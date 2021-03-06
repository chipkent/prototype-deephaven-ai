
# This example demonstrates a case where a user function creates partial tensors for each row.
# These partial tensors are aggregated into tensors before evaluating the model.  
# The aggregation should result in more efficient use of the AI machinery.  
# The model function is then evaluated for each row to create results for the row.

################################################################################################################################
# Everything here would be part of a DH library
################################################################################################################################

from deephaven import QueryScope
import jpy

class Input:
    def __init__(self, columns, gather):
        if type(columns) is list: 
            self.columns = columns
        else:
            self.columns = [columns]

        self.gather = gather

class Output:
    def __init__(self, column, scatter, col_type="java.lang.Object"):
        self.column = column
        self.scatter = scatter
        self.col_type = col_type

#TODO: this should be implemented in Java for speed.  This efficiently iterates over the indices in multiple index sets.  Works for hist and real time.
class IndexSetIterator:
    def __init__(self, *indexes):
        self.indexes = indexes

    def __len__(self):
        rst = 0

        for index in self.indexes:
            rst += index.size()

        return rst

    def __iter__(self):
        for index in self.indexes:
            it = index.iterator()

            while it.hasNext():
                yield it.next()


#TODO: clearly in production code there would need to be extensive testing of inputs and outputs (e.g. no null, correct size, ...)
#TODO: ths is a static example, real time requires more work
#TODO: this can be performance tuned
def ai_eval(table=None, model=None, inputs=[], outputs=[]):
    print("SETUP")
    col_sets = [ [ table.getColumnSource(col) for col in input.columns ] for input in inputs ]

    print("GATHER")
    #TODO: for real time, the IndexSetIterator would be populated with the ADD and MODIFY indices
    idx = IndexSetIterator(table.getIndex())
    gathered = [ input.gather(idx, col_set) for (input,col_set) in zip(inputs,col_sets) ]

    print("COMPUTE NEW DATA")
    output_values = model(*gathered)

    print("POPULATE OUTPUT TABLE")
    rst = table.by()
    n = table.size()

    for output in outputs:
        print(f"GENERATING OUTPUT: {output.column}")
        #TODO: maybe we can infer the type?
        data = jpy.array(output.col_type, n)

        #TODO: python looping is slow.  should avoid or numba it
        for i in range(n):
            data[i] = output.scatter(output_values, i)

        QueryScope.addParam("__temp", data)
        rst = rst.update(f"{output.column} = __temp")

    return rst.ungroup()



################################################################################################################################
# Everything here would be user created -- or maybe part of a DH library if it is common functionality
################################################################################################################################

import random
import numpy as np
from math import sqrt
from deephaven.TableTools import emptyTable

class ZNugget:
    def __init__(self, payload):
        self.payload = payload

def make_z(x):
    return ZNugget([random.randint(4,11)+x for z in range(5)])

def gather_2d(idx, cols):
    rst = np.empty([len(idx), len(cols)], dtype=np.float64)

    for (i,kk) in enumerate(idx):
        for (j,col) in enumerate(cols):
            rst[i,j] = col.get(kk)

    return rst

def gather_znugget(idx, cols):
    if len(cols) != 1:
        raise Exception("Expected 1 column")

    col = cols[0]

    n = 5
    rst = np.empty([len(idx), n], dtype=np.float64)

    for (i,kk) in enumerate(idx):
        val = col.get(kk).payload

        for j in range(n):
            rst[i,j] = val[j]

    return rst

def scatter_a(data, i):
    return int(data[0][i])

def scatter_b(data, i):
    return float(data[1][i,1])

def scatter_c(data, i):
    return float(sqrt(data[2][i,1] + data[1][i,1]))

def model_func(a,b,c):
    return 3*a, b+11, b + 32

t = emptyTable(10).update("X = i", "Y = sqrt(X)")
t2 = t.update("Z = make_z(X)")
t3 = ai_eval(table=t2, model=model_func, inputs=[Input("X", gather_2d), Input(["X", "Y"], gather_2d), Input("Z", gather_znugget)], outputs=[Output("A",scatter_a, col_type="int"), Output("B",scatter_b), Output("C",scatter_c)])

#TODO: dropping weird column types to avoid some display bugs
meta2 = t2.getMeta()
t2 = t2.dropColumns("Z")
meta3 = t3.getMeta()
t3 = t3.dropColumns("Z", "B", "C")