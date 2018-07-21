import unittest
import pandas as pd
import sys
from sqlalchemy import create_engine

sys.path.append('../')
from rapid import *
R = lambda x: round(x, 2)

class TestRapidFetchData(unittest.TestCase):

	def setUp(self):
		self.con = create_engine('sqlite:///data.sqlite3')
		self.tbl = 'eod'

	def test_fetch_data(self):
		"""
		Additional date to be included for correct results due to
		"""
		universe = ['one', 'two']
		start, end = '2018-01-01 00:00:00.000000', '2018-01-02 00:00:00.000000'
		data = fetch_data(universe, start, end, self.con, self.tbl)
		self.assertEqual(data.shape[0], 4)

		universe = ['one', 'two', 'six']
		data = fetch_data(universe, start, end, self.con, self.tbl)
		self.assertEqual(data.shape[0], 6)

		end = '2018-01-06 00:00:00.000000'
		universe.append('five')
		data = fetch_data(universe, start, end, self.con, self.tbl)
		self.assertEqual(data.shape[0], 24)

	def test_fetch_data_condition(self):
		universe = ['one', 'two', 'three', 'four', 'five', 'six']
		start, end = '2018-01-01 00:00:00.000000', '2018-01-06 00:00:00.000000'
		condition = ['open > 100']
		data = fetch_data(universe, start, end, self.con, self.tbl,
				where_clause = condition)		
		self.assertEqual(data.shape[0], 17)
		condition.append('volume > 200000')
		data = fetch_data(universe, start, end, self.con, self.tbl,
				where_clause = condition)		
		self.assertEqual(data.shape[0], 12)

class TestRapidPrepareData(unittest.TestCase):

	#TO DO: return in case of Empty dataframe
	def setUp(self):
		from sqlalchemy import create_engine
		con = create_engine('sqlite:///data.sqlite3')
		tbl = 'eod'
		universe = ['one', 'two', 'three', 'four', 'five', 'six']
		start, end = '2018-01-01 00:00:00.000000', '2018-01-06 00:00:00.000000'
		self.data = fetch_data(universe, start, end, con, tbl)

	def test_prepare_data(self):
		self.assertEqual(self.data.shape[0], 36)
		self.assertEqual(self.data.shape[1], 8)

		columns = [
			{'F': {'formula': '(open+close)/2', 'col_name': 'avgprice'}},
			{'I': {'indicator': 'SMA', 'period': 3, 'lag': 1, 'col_name': 'SMA3'}}
		]
		conditions = [
			{'F': {'formula': 'open > prevclose', 'col_name': 'sig1'}},
			{'F': {'formula': 'open < sma3', 'col_name': 'sig2'}}
		]
		data = prepare_data(self.data, columns)
		self.assertEqual(data.shape[1], 10)
		data = prepare_data(data, conditions)
		self.assertEqual(data.shape[1], 12)
		self.assertEqual(data.query('sig1==1').shape[0], 20)
		self.assertEqual(data.query('sig2==1').shape[0], 5)	

class TestRapidApplyPrices(unittest.TestCase):
	def setUp(self):
		from sqlalchemy import create_engine
		con = create_engine('sqlite:///data.sqlite3')
		tbl = 'eod'
		universe = ['one', 'two', 'three', 'four', 'five', 'six']
		start, end = '2018-01-01 00:00:00.000000', '2018-01-06 00:00:00.000000'
		self.data = fetch_data(universe, start, end, con, tbl)

	def test_apply_price_buy(self):
		# Simple default parameters
		idx = pd.IndexSlice
		R = lambda x: round(x, 2)
		conditions = ['open > prevclose']
		df = apply_prices(self.data, conditions, 'open', 3, 'B')
		self.assertEqual(df.shape[0], 20)
		df.set_index(['timestamp', 'symbol'], inplace=True)
		self.assertEqual(df.at[idx['2018-01-06', 'one'], 'price'], 10.65)
		self.assertEqual(df.query('low <= stop_loss').shape[0], 7)
		self.assertEqual(df.query('low <= stop_loss').price.sum(), 562.45)
		self.assertEqual(df.at[idx['2018-01-05', 'four'], 'sell'], 169.25)
		self.assertEqual(df.at[idx['2018-01-05', 'six'], 'sell'], 63.45)
		self.assertEqual(R(df.at[idx['2018-01-05', 'five'], 'stop_loss']), 25.70)
		self.assertEqual(df.at[idx['2018-01-05', 'five'], 'sell'], 27.4)

	def test_apply_price_sell(self):
		idx = pd.IndexSlice
		R = lambda x: round(x, 2)
		conditions = ['open > prevclose']
		df = apply_prices(self.data, conditions, 'open', 3, 'S')
		df.set_index(['timestamp', 'symbol'], inplace=True)
		self.assertEqual(df.query('stop_loss >= high').shape[0], 13)
		self.assertEqual(R(df.at[idx['2018-01-02', 'three'], 'stop_loss']), 105.05)
		self.assertEqual(df.at[idx['2018-01-05', 'four'], 'price'], 174.5)
		self.assertEqual(df.at[idx['2018-01-03', 'three'], 'buy'], 110)	

	def test_order_raise_error(self):
		pass

class TestRapidRunStrategy(unittest.TestCase):

	def setUp(self):
		from sqlalchemy import create_engine
		con = create_engine('sqlite:///data.sqlite3')
		tbl = 'eod'
		universe = ['one', 'two', 'three', 'four', 'five', 'six']
		start, end = '2018-01-01 00:00:00.000000', '2018-01-06 00:00:00.000000'
		data = fetch_data(universe, start, end, con, tbl)
		conditions = ['open > prevclose']
		self.data = apply_prices(data, conditions, 'open', 3, 'B')

	def test_run_strategy_simple(self):
		result = run_strategy(self.data, 100000, 1, 5, 'price', True)
		self.assertEqual(R(result.profit.sum()), -715.09)
		self.assertEqual(result.qty.sum(), 26506)
		by_day = result.groupby('timestamp').profit.sum()
		self.assertEqual(R(by_day.loc['2018-01-04']), -3153.15)

class TestBackTest(unittest.TestCase):
	def setUp(self):
		from sqlalchemy import create_engine
		con = create_engine('sqlite:///data.sqlite3')
		tbl = 'eod'
		from functools import partial
		self.bt = partial(backtest, connection=con, tablename=tbl)
		import yaml
		with open('backtest.yaml') as f:
			self.kwargs = yaml.load(f)

	def test_strategy_one(self):
		kwargs = self.kwargs[0]
		result = self.bt(**kwargs)
		self.assertEqual(R(result.profit.sum()), -715.09)
		kwargs.update({'leverage': 2})
		result = self.bt(**kwargs)
		self.assertEqual(R(result.profit.sum()), -1429.31)
		kwargs.update({'capital': 10000, 'leverage': 10})
		result = self.bt(**kwargs)
		self.assertEqual(R(result.profit.sum()), -715.09)

def test_empty_dataframe_result():
	"""
	Program to terminate in case there is no result at any stage
	"""
	pass

def test_stop_loss_zero():
	pass

if __name__ == '__main__':
    unittest.main()