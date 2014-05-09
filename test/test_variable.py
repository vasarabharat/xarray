from collections import namedtuple, OrderedDict
from copy import copy, deepcopy
from datetime import datetime
from textwrap import dedent

import numpy as np
import pandas as pd

from xray import Variable, Dataset, DataArray
from xray.variable import (Coordinate, as_variable, NumpyArrayAdapter,
                           PandasIndexAdapter)

from . import TestCase, source_ndarray


class VariableSubclassTestCases(object):
    def test_properties(self):
        data = 0.5 * np.arange(10)
        v = self.cls(['time'], data, {'foo': 'bar'})
        self.assertEqual(v.dimensions, ('time',))
        self.assertArrayEqual(v.values, data)
        self.assertEqual(v.dtype, float)
        self.assertEqual(v.shape, (10,))
        self.assertEqual(v.size, 10)
        self.assertEqual(v.ndim, 1)
        self.assertEqual(len(v), 10)
        self.assertEqual(v.attrs, {'foo': u'bar'})

    def test_attrs(self):
        v = self.cls(['time'], 0.5 * np.arange(10))
        self.assertEqual(v.attrs, {})
        attrs = {'foo': 'bar'}
        v.attrs = attrs
        self.assertEqual(v.attrs, attrs)
        self.assertIsInstance(v.attrs, OrderedDict)
        v.attrs['foo'] = 'baz'
        self.assertEqual(v.attrs['foo'], 'baz')

    def test_0d_data(self):
        d = datetime(2000, 1, 1)
        for value, dtype in [(0, int),
                             (np.float32(0.5), np.float32),
                             ('foo', np.str_),
                             (d, None),
                             (np.datetime64(d), np.datetime64)]:
            x = self.cls(['x'], [value])
            # check array properties
            self.assertEqual(x[0].shape, ())
            self.assertEqual(x[0].ndim, 0)
            self.assertEqual(x[0].size, 1)
            # test identity
            self.assertTrue(x.equals(x.copy()))
            self.assertTrue(x.identical(x.copy()))
            # check value is equal for both ndarray and Variable
            self.assertEqual(x.values[0], value)
            self.assertEqual(x[0].values, value)
            # check type or dtype is consistent for both ndarray and Variable
            if dtype is None:
                # check output type instead of array dtype
                self.assertEqual(type(x.values[0]), type(value))
                self.assertEqual(type(x[0].values), type(value))
            else:
                assert np.issubdtype(x.values[0].dtype, dtype), (x.values[0].dtype, dtype)
                assert np.issubdtype(x[0].values.dtype, dtype), (x[0].values.dtype, dtype)

    def test_0d_time_data(self):
        # regression test for #105
        x = self.cls('time', pd.date_range('2000-01-01', periods=5))
        expected = np.datetime64('2000-01-01T00Z', 'ns')
        self.assertEqual(x[0].values, expected)

    def test_pandas_data(self):
        v = self.cls(['x'], pd.Series([0, 1, 2], index=[3, 2, 1]))
        self.assertVariableIdentical(v, v[[0, 1, 2]])
        v = self.cls(['x'], pd.Index([0, 1, 2]))
        self.assertEqual(v[0].values, v.values[0])

    def test_1d_math(self):
        x = 1.0 * np.arange(5)
        y = np.ones(5)
        v = self.cls(['x'], x)
        # unary ops
        self.assertVariableIdentical(v, +v)
        self.assertVariableIdentical(v, abs(v))
        self.assertArrayEqual((-v).values, -x)
        # bianry ops with numbers
        self.assertVariableIdentical(v, v + 0)
        self.assertVariableIdentical(v, 0 + v)
        self.assertVariableIdentical(v, v * 1)
        self.assertArrayEqual((v > 2).values, x > 2)
        self.assertArrayEqual((0 == v).values, 0 == x)
        self.assertArrayEqual((v - 1).values, x - 1)
        self.assertArrayEqual((1 - v).values, 1 - x)
        # binary ops with numpy arrays
        self.assertArrayEqual((v * x).values, x ** 2)
        self.assertArrayEqual((x * v).values, x ** 2)
        self.assertArrayEqual(v - y, v - 1)
        self.assertArrayEqual(y - v, 1 - v)
        # verify attributes are dropped
        v2 = self.cls(['x'], x, {'units': 'meters'})
        self.assertVariableIdentical(v, +v2)
        # binary ops with all variables
        self.assertArrayEqual(v + v, 2 * v)
        w = self.cls(['x'], y, {'foo': 'bar'})
        self.assertVariableIdentical(v + w, self.cls(['x'], x + y))
        self.assertArrayEqual((v * w).values, x * y)
        # something complicated
        self.assertArrayEqual((v ** 2 * w - 1 + x).values, x ** 2 * y - 1 + x)
        # make sure dtype is preserved (for Coordinates)
        self.assertEqual(float, (+v).dtype)
        self.assertEqual(float, (+v).values.dtype)
        self.assertEqual(float, (0 + v).dtype)
        self.assertEqual(float, (0 + v).values.dtype)
        # check types of returned data
        self.assertIsInstance(+v, Variable)
        self.assertNotIsInstance(+v, Coordinate)
        self.assertIsInstance(0 + v, Variable)
        self.assertNotIsInstance(0 + v, Coordinate)

    def test_1d_reduce(self):
        x = np.arange(5)
        v = self.cls(['x'], x)
        actual = v.sum()
        expected = Variable((), 10)
        self.assertVariableIdentical(expected, actual)
        self.assertIs(type(actual), Variable)

    def test_array_interface(self):
        x = np.arange(5)
        v = self.cls(['x'], x)
        self.assertArrayEqual(np.asarray(v), x)
        # test patched in methods
        self.assertArrayEqual(v.astype(float), x.astype(float))
        self.assertVariableIdentical(v.argsort(), v)
        self.assertVariableIdentical(v.clip(2, 3), self.cls('x', x.clip(2, 3)))
        # test ufuncs
        self.assertVariableIdentical(np.sin(v), self.cls(['x'], np.sin(x)))
        self.assertIsInstance(np.sin(v), Variable)
        self.assertNotIsInstance(np.sin(v), Coordinate)

    def example_1d_objects(self):
        for data in [range(3),
                     0.5 * np.arange(3),
                     0.5 * np.arange(3, dtype=np.float32),
                     pd.date_range('2000-01-01', periods=3),
                     np.array(['a', 'b', 'c'], dtype=object)]:
            yield (self.cls('x', data), data)

    def test___array__(self):
        for v, data in self.example_1d_objects():
            self.assertArrayEqual(v.values, np.asarray(data))
            self.assertArrayEqual(np.asarray(v), np.asarray(data))
            self.assertEqual(v[0].values, np.asarray(data)[0])
            self.assertEqual(np.asarray(v[0]), np.asarray(data)[0])

    def test_equals_all_dtypes(self):
        for v, _ in self.example_1d_objects():
            v2 = v.copy()
            self.assertTrue(v.equals(v2))
            self.assertTrue(v.identical(v2))
            self.assertTrue(v[0].equals(v2[0]))
            self.assertTrue(v[0].identical(v2[0]))
            self.assertTrue(v[:2].equals(v2[:2]))
            self.assertTrue(v[:2].identical(v2[:2]))

    def test_concat(self):
        x = np.arange(5)
        y = np.ones(5)
        v = self.cls(['a'], x)
        w = self.cls(['a'], y)
        self.assertVariableIdentical(Variable(['b', 'a'], np.array([x, y])),
                               Variable.concat([v, w], 'b'))
        self.assertVariableIdentical(Variable(['b', 'a'], np.array([x, y])),
                               Variable.concat((v, w), 'b'))
        self.assertVariableIdentical(Variable(['b', 'a'], np.array([x, y])),
                               Variable.concat((v, w), 'b', length=2))
        with self.assertRaisesRegexp(ValueError, 'actual length'):
            Variable.concat([v, w], 'b', length=1)
        with self.assertRaisesRegexp(ValueError, 'actual length'):
            Variable.concat([v, w, w], 'b', length=4)
        with self.assertRaisesRegexp(ValueError, 'inconsistent dimensions'):
            Variable.concat([v, Variable(['c'], y)], 'b')
        # test concatenating along a dimension
        v = Variable(['time', 'x'], np.random.random((10, 8)))
        self.assertVariableIdentical(v, Variable.concat([v[:5], v[5:]], 'time'))
        self.assertVariableIdentical(v, Variable.concat([v[:5], v[5], v[6:]], 'time'))
        self.assertVariableIdentical(v, Variable.concat([v[0], v[1:]], 'time'))
        # test dimension order
        self.assertVariableIdentical(v, Variable.concat([v[:, :5], v[:, 5:]], 'x'))
        self.assertVariableIdentical(v.transpose(),
                               Variable.concat([v[:, 0], v[:, 1:]], 'x'))

    def test_copy(self):
        v = self.cls('x', 0.5 * np.arange(10), {'foo': 'bar'})
        for deep in [True, False]:
            w = v.copy(deep=deep)
            self.assertIs(type(v), type(w))
            self.assertVariableIdentical(v, w)
            self.assertEqual(v.dtype, w.dtype)
            if self.cls is Variable:
                if deep:
                    self.assertIsNot(source_ndarray(v.values),
                                     source_ndarray(w.values))
                else:
                    self.assertIs(source_ndarray(v.values),
                                  source_ndarray(w.values))
        self.assertVariableIdentical(v, copy(v))


class TestVariable(TestCase, VariableSubclassTestCases):
    cls = staticmethod(Variable)

    def setUp(self):
        self.d = np.random.random((10, 3)).astype(np.float64)

    def test_data(self):
        v = Variable(['time', 'x'], self.d)
        self.assertArrayEqual(v.values, self.d)
        self.assertIs(source_ndarray(v.values), self.d)
        with self.assertRaises(ValueError):
            # wrong size
            v.values = np.random.random(5)
        d2 = np.random.random((10, 3))
        v.values = d2
        self.assertIs(source_ndarray(v.values), d2)

    def test_item(self):
        v = Variable([], np.float32(0.0))
        self.assertEquals(v.item(), 0)
        self.assertIs(type(v.item()), float)

    def test_equals_and_identical(self):
        d = np.random.rand(10, 3)
        d[0, 0] = np.nan
        v1 = Variable(('dim1', 'dim2'), data=d,
                       attributes={'att1': 3, 'att2': [1, 2, 3]})
        v2 = Variable(('dim1', 'dim2'), data=d,
                       attributes={'att1': 3, 'att2': [1, 2, 3]})
        self.assertTrue(v1.equals(v2))
        self.assertTrue(v1.identical(v2))

        v3 = Variable(('dim1', 'dim3'), data=d)
        self.assertFalse(v1.equals(v3))

        v4 = Variable(('dim1', 'dim2'), data=d)
        self.assertTrue(v1.equals(v4))
        self.assertFalse(v1.identical(v4))

        v5 = deepcopy(v1)
        v5.values[:] = np.random.rand(10, 3)
        self.assertFalse(v1.equals(v5))

        self.assertFalse(v1.equals(None))
        self.assertFalse(v1.equals(d))

        self.assertFalse(v1.identical(None))
        self.assertFalse(v1.identical(d))

    def test_as_variable(self):
        data = np.arange(10)
        expected = Variable('x', data)

        self.assertVariableIdentical(expected, as_variable(expected))

        ds = Dataset({'x': expected})
        self.assertVariableIdentical(expected, as_variable(ds['x']))
        self.assertNotIsInstance(ds['x'], Variable)
        self.assertIsInstance(as_variable(ds['x']), Variable)
        self.assertIsInstance(as_variable(ds['x'], strict=False), DataArray)

        FakeVariable = namedtuple('FakeVariable', 'values dimensions')
        fake_xarray = FakeVariable(expected.values, expected.dimensions)
        self.assertVariableIdentical(expected, as_variable(fake_xarray))

        xarray_tuple = (expected.dimensions, expected.values)
        self.assertVariableIdentical(expected, as_variable(xarray_tuple))

        with self.assertRaisesRegexp(TypeError, 'cannot convert numpy'):
            as_variable(data)
        with self.assertRaisesRegexp(TypeError, 'cannot convert arg'):
            as_variable(list(data))


    def test_repr(self):
        v = Variable(['time', 'x'], [[1, 2, 3], [4, 5, 6]], {'foo': 'bar'})
        expected = dedent("""
        <xray.Variable (time: 2, x: 3)>
        array([[1, 2, 3],
               [4, 5, 6]])
        Attributes:
            foo: bar
        """).strip()
        self.assertEqual(expected, repr(v))

    def test_items(self):
        data = np.random.random((10, 11))
        v = Variable(['x', 'y'], data)
        # test slicing
        self.assertVariableIdentical(v, v[:])
        self.assertVariableIdentical(v, v[...])
        self.assertVariableIdentical(Variable(['y'], data[0]), v[0])
        self.assertVariableIdentical(Variable(['x'], data[:, 0]), v[:, 0])
        self.assertVariableIdentical(Variable(['x', 'y'], data[:3, :2]),
                                     v[:3, :2])
        # test array indexing
        x = Variable(['x'], np.arange(10))
        y = Variable(['y'], np.arange(11))
        self.assertVariableIdentical(v, v[x.values])
        self.assertVariableIdentical(v, v[x])
        self.assertVariableIdentical(v[:3], v[x < 3])
        self.assertVariableIdentical(v[:, 3:], v[:, y >= 3])
        self.assertVariableIdentical(v[:3, 3:], v[x < 3, y >= 3])
        self.assertVariableIdentical(v[:3, :2], v[x[:3], y[:2]])
        self.assertVariableIdentical(v[:3, :2], v[range(3), range(2)])
        # test iteration
        for n, item in enumerate(v):
            self.assertVariableIdentical(Variable(['y'], data[n]), item)
        with self.assertRaisesRegexp(TypeError, 'iteration over a 0-d'):
            iter(Variable([], 0))
        # test setting
        v.values[:] = 0
        self.assertTrue(np.all(v.values == 0))
        # test orthogonal setting
        v[range(10), range(11)] = 1
        self.assertArrayEqual(v.values, np.ones((10, 11)))

    def test_indexed(self):
        v = Variable(['time', 'x'], self.d)
        self.assertVariableIdentical(v.indexed(time=slice(None)), v)
        self.assertVariableIdentical(v.indexed(time=0), v[0])
        self.assertVariableIdentical(v.indexed(time=slice(0, 3)), v[:3])
        self.assertVariableIdentical(v.indexed(x=0), v[:, 0])
        with self.assertRaisesRegexp(ValueError, 'do not exist'):
            v.indexed(not_a_dim=0)

    def test_transpose(self):
        v = Variable(['time', 'x'], self.d)
        v2 = Variable(['x', 'time'], self.d.T)
        self.assertVariableIdentical(v, v2.transpose())
        self.assertVariableIdentical(v.transpose(), v.T)
        x = np.random.randn(2, 3, 4, 5)
        w = Variable(['a', 'b', 'c', 'd'], x)
        w2 = Variable(['d', 'b', 'c', 'a'], np.einsum('abcd->dbca', x))
        self.assertEqual(w2.shape, (5, 3, 4, 2))
        self.assertVariableIdentical(w2, w.transpose('d', 'b', 'c', 'a'))
        self.assertVariableIdentical(w, w2.transpose('a', 'b', 'c', 'd'))
        w3 = Variable(['b', 'c', 'd', 'a'], np.einsum('abcd->bcda', x))
        self.assertVariableIdentical(w, w3.transpose('a', 'b', 'c', 'd'))

    def test_squeeze(self):
        v = Variable(['x', 'y'], [[1]])
        self.assertVariableIdentical(Variable([], 1), v.squeeze())
        self.assertVariableIdentical(Variable(['y'], [1]), v.squeeze('x'))
        self.assertVariableIdentical(Variable(['y'], [1]), v.squeeze(['x']))
        self.assertVariableIdentical(Variable(['x'], [1]), v.squeeze('y'))
        self.assertVariableIdentical(Variable([], 1), v.squeeze(['x', 'y']))

        v = Variable(['x', 'y'], [[1, 2]])
        self.assertVariableIdentical(Variable(['y'], [1, 2]), v.squeeze())
        self.assertVariableIdentical(Variable(['y'], [1, 2]), v.squeeze('x'))
        with self.assertRaisesRegexp(ValueError, 'cannot select a dimension'):
            v.squeeze('y')

    def test_get_axis_num(self):
        v = Variable(['x', 'y', 'z'], np.random.randn(2, 3, 4))
        self.assertEqual(v.get_axis_num('x'), 0)
        self.assertEqual(v.get_axis_num(['x']), (0,))
        self.assertEqual(v.get_axis_num(['x', 'y']), (0, 1))
        self.assertEqual(v.get_axis_num(['z', 'y', 'x']), (2, 1, 0))
        with self.assertRaisesRegexp(ValueError, 'not found in array dim'):
            v.get_axis_num('foobar')

    def test_broadcasting_math(self):
        x = np.random.randn(2, 3)
        v = Variable(['a', 'b'], x)
        # 1d to 2d broadcasting
        self.assertVariableIdentical(
            v * v,
            Variable(['a', 'b'], np.einsum('ab,ab->ab', x, x)))
        self.assertVariableIdentical(
            v * v[0],
            Variable(['a', 'b'], np.einsum('ab,b->ab', x, x[0])))
        self.assertVariableIdentical(
            v[0] * v,
            Variable(['b', 'a'], np.einsum('b,ab->ba', x[0], x)))
        self.assertVariableIdentical(
            v[0] * v[:, 0],
            Variable(['b', 'a'], np.einsum('b,a->ba', x[0], x[:, 0])))
        # higher dim broadcasting
        y = np.random.randn(3, 4, 5)
        w = Variable(['b', 'c', 'd'], y)
        self.assertVariableIdentical(
            v * w, Variable(['a', 'b', 'c', 'd'],
                            np.einsum('ab,bcd->abcd', x, y)))
        self.assertVariableIdentical(
            w * v, Variable(['b', 'c', 'd', 'a'],
                            np.einsum('bcd,ab->bcda', y, x)))
        self.assertVariableIdentical(
            v * w[0], Variable(['a', 'b', 'c', 'd'],
                               np.einsum('ab,cd->abcd', x, y[0])))

    def test_broadcasting_failures(self):
        a = Variable(['x'], np.arange(10))
        b = Variable(['x'], np.arange(5))
        c = Variable(['x', 'x'], np.arange(100).reshape(10, 10))
        with self.assertRaisesRegexp(ValueError, 'mismatched lengths'):
            a + b
        with self.assertRaisesRegexp(ValueError, 'duplicate dimensions'):
            a + c

    def test_inplace_math(self):
        x = np.arange(5)
        v = Variable(['x'], x)
        v2 = v
        v2 += 1
        self.assertIs(v, v2)
        # since we provided an ndarray for data, it is also modified in-place
        self.assertIs(source_ndarray(v.values), x)
        self.assertArrayEqual(v.values, np.arange(5) + 1)

        with self.assertRaisesRegexp(ValueError, 'dimensions cannot change'):
            v += Variable('y', np.arange(5))

    def test_reduce(self):
        v = Variable(['x', 'y'], self.d, {'ignored': 'attributes'})
        self.assertVariableIdentical(v.reduce(np.std, 'x'),
                                     Variable(['y'], self.d.std(axis=0)))
        self.assertVariableIdentical(v.reduce(np.std, axis=0),
                                     v.reduce(np.std, dimension='x'))
        self.assertVariableIdentical(v.reduce(np.std, ['y', 'x']),
                                     Variable([], self.d.std(axis=(0, 1))))
        self.assertVariableIdentical(v.reduce(np.std),
                                     Variable([], self.d.std()))
        self.assertVariableIdentical(
            v.reduce(np.mean, 'x').reduce(np.std, 'y'),
            Variable([], self.d.mean(axis=0).std()))
        self.assertVariableIdentical(v.mean('x'), v.reduce(np.mean, 'x'))

        with self.assertRaisesRegexp(ValueError, 'cannot supply both'):
            v.mean(dimension='x', axis=0)


class TestCoordinate(TestCase, VariableSubclassTestCases):
    cls = staticmethod(Coordinate)

    def test_init(self):
        with self.assertRaisesRegexp(ValueError, 'must be 1-dimensional'):
            Coordinate((), 0)

    def test_as_index(self):
        data = 0.5 * np.arange(10)
        v = Coordinate(['time'], data, {'foo': 'bar'})
        self.assertTrue(pd.Index(data).equals(v.as_index))

    def test_data(self):
        x = Coordinate('x', np.arange(3.0))
        # data should be initially saved as an ndarray
        self.assertIs(type(x._data), NumpyArrayAdapter)
        self.assertEqual(float, x.dtype)
        self.assertArrayEqual(np.arange(3), x)
        self.assertEqual(float, x.values.dtype)
        # after inspecting x.values, the Coordinate will be saved as an Index
        self.assertIsInstance(x._data, PandasIndexAdapter)
        with self.assertRaisesRegexp(TypeError, 'cannot be modified'):
            x[:] = 0
