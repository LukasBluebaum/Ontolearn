import datetime
import os
import pickle
import time
import copy
from queue import PriorityQueue
from typing import Tuple, Set


def performance_debugger(func_name):
    def function_name_decoratir(func):
        def debug(*args, **kwargs):
            long_string = ''
            starT = time.time()
            # print('######', func_name, ' func ', end=' ')
            r = func(*args, **kwargs)
            print(func_name, ' took ', round(time.time() - starT, 4), ' seconds')
            #           long_string += str(func_name) + ' took:' + str(time.time() - starT) + ' seconds'

            return r

        return debug

    return function_name_decoratir


def decompose(number, upperlimit, bisher, combosTmp):
    """
    TODO: Explain why we need it. We have simply hammered the java code into python here
    TODO: After fully understanding, we could optimize the computation if necessary
    TODO: By simply vectorizing the computations.
    :param number:
    :param upperlimit:
    :param bisher:
    :param combosTmp:
    :return:
    """
    i = min(number, upperlimit)
    while i >= 1:
        newbisher = list()

        if i == 0:
            newbisher = bisher
            newbisher.append(i)
        elif number - i != 1:
            newbisher = copy.copy(bisher)
            newbisher.append(i)

        if number - i > 1:
            decompose(number - i - 1, i, newbisher, combosTmp)
        elif number - i == 0:
            combosTmp.append(newbisher)

        i -= 1


def getCombos(length: int, max_length: int):
    """
    	/**
	 * Methods for computing combinations with the additional restriction
	 * that <code>maxValue</code> is the highest natural number, which can
	 * occur.
	 * @see #getCombos(int)
	 * @param length Length of construct.
	 * @param maxValue Maximum value which can occur in sum.
	 * @return A two dimensional list constructed in {@link #getCombos(int)}.
	 */

    :param i:
    :param max_length:
    :return:
    """
    combosTmp = []
    decompose(length, max_length, [], combosTmp)
    return combosTmp


def incCrossProduct(baseset, newset, exp_gen):
    retset = set()

    if len(baseset) == 0:
        for c in newset:
            retset.add(c)
        return retset
    for i in baseset:
        for j in newset:
            retset.add(exp_gen.union(i, j))
    return retset


def create_experiment_folder(folder_name='Experiments'):
    directory = os.getcwd() + '/' + folder_name + '/'
    folder_name = str(datetime.datetime.now())
    path_of_folder = directory + folder_name
    os.makedirs(path_of_folder)
    return path_of_folder, path_of_folder[:path_of_folder.rfind('/')]






def serializer(*, object_: object, path: str, serialized_name: str):
    with open(path + '/' + serialized_name + ".p", "wb") as f:
        pickle.dump(object_, f)
    f.close()


def deserializer(*, path: str, serialized_name: str):
    with open(path + "/" + serialized_name + ".p", "rb") as f:
        obj_ = pickle.load(f)
    f.close()
    return obj_
