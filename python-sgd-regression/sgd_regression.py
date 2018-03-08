#!/usr/bin/env python3

from mip_helper import io_helper, shapes
from sklearn_to_pfa.sklearn_to_pfa import sklearn_to_pfa
from sklearn_to_pfa.featurizer import Featurizer, Standardize, OneHotEncoding

import logging
import json
import argparse

import pandas as pd
from sklearn.linear_model import SGDRegressor, SGDClassifier
import jsonpickle
import jsonpickle.ext.numpy as jsonpickle_numpy
jsonpickle_numpy.register_handlers()


# Configure logging
logging.basicConfig(level=logging.INFO)


DEFAULT_DOCKER_IMAGE = "python-sgd-regression"


def main(job_id, generate_pfa):
    inputs = io_helper.fetch_data()
    dep_var = inputs["data"]["dependent"][0]
    indep_vars = inputs["data"]["independent"]

    if dep_var['type']['name'] in ('polynominal', 'binominal'):
        job_type = 'classification'
    else:
        job_type = 'regression'

    # Get existing results with partial model if they exist
    if job_id:
        job_result = io_helper.get_results(job_id=str(job_id))

        logging.info('Loading existing estimator')
        # reconstruct estimator from metadata in PFA
        estimator = deserialize_sklearn_estimator(job_result.data)
    else:
        logging.info('Creating new estimator')
        # TODO: SGD-type algorithms require normalized data! how do we do that in incremental learning?
        #   see http://dask-ml.readthedocs.io/en/latest/modules/generated/dask_ml.preprocessing.StandardScaler.html#dask_ml.preprocessing.StandardScaler.partial_fit
        #   for inspiration
        # TODO: add optional parameters to `SGDRegressor`
        # TODO: add more estimators like NaiveBayes, MLPRegressor, etc.
        if job_type == 'regression':
            estimator = SGDRegressor()
        elif job_type == 'classification':
            estimator = SGDClassifier()

    # Check dependent variable type (should be continuous)
    # TODO: probably redundant block of code
    if job_type == 'regression':
        if dep_var["type"]["name"] not in ["integer", "real"]:
            logging.warning("Dependent variable should be continuous!")
            return None
    elif job_type == 'classification':
        if dep_var["type"]["name"] not in ['polynominal', 'binominal']:
            logging.warning("Dependent variable needs to be categorical!")
            return None

    # featurization
    transforms = []
    for var in indep_vars:
        if var['type']['name'] in ('integer', 'real'):
            transforms.append(Standardize(var['name'], var['mean'], var['std']))
        elif var["type"]["name"] in ['polynominal', 'binominal']:
            transforms.append(OneHotEncoding(var['name'], var['enumeration']))

    featurizer = Featurizer(transforms)

    # convert variables into dataframe
    X, y = get_Xy(dep_var, indep_vars)
    X = featurizer.transform(X)

    # Drop NaN values
    # TODO: how should we treat NaNs?
    is_null = (pd.isnull(X).any(1) | pd.isnull(y)).values
    X = X[~is_null, :]
    y = y[~is_null]

    # Train single step
    if job_type == 'classification':
        estimator.partial_fit(X, y, classes=dep_var['type']['enumeration'])
    else:
        estimator.partial_fit(X, y)

    serialized_estimator = serialize_sklearn_estimator(estimator)

    if generate_pfa:
        # Create PFA from the estimator
        types = [(var['name'], var['type']['name']) for var in indep_vars]
        pfa = sklearn_to_pfa(estimator, types, featurizer.generate_pretty_pfa())

        # Add serialized model as metadata
        pfa['metadata'] = {
            'estimator': serialized_estimator
        }

        # Save or update job_result
        logging.info('Saving PFA to job_results table')
        pfa = json.dumps(pfa)
        io_helper.save_results(pfa, '', shapes.Shapes.PFA)
    else:
        # Save or update job_result
        logging.info('Saving serialized estimator into job_results table')
        io_helper.save_results(serialized_estimator, '', shapes.Shapes.JSON)


def serialize_sklearn_estimator(estimator):
    """Serialize model to JSON, see https://cmry.github.io/notes/serialize for inspiration."""
    return jsonpickle.encode(estimator)


def deserialize_sklearn_estimator(js):
    """Deserialize model from JSON."""
    return jsonpickle.decode(js)


def get_Xy(dep_var, indep_vars):
    """Create dataframe from input data.
    :param dep_var:
    :param indep_vars:
    :return: dataframe with data from all variables
    """
    df = {}
    for var in [dep_var] + indep_vars:
        # categorical variable - we need to add all categories to make one-hot encoding work right
        if 'enumeration' in var['type']:
            df[var['name']] = pd.Categorical(var['series'], categories=var['type']['enumeration'])
        else:
            # infer type automatically
            df[var['name']] = var['series']
    X = pd.DataFrame(df)
    y = X[dep_var['name']]
    del X[dep_var['name']]
    return X, y


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('compute', choices=['compute'])
    parser.add_argument('mode', choices=['partial', 'final'])
    parser.add_argument('--job-id', type=int)

    args = parser.parse_args()

    # > compute partial --job-id 12
    if args.mode == 'partial':
        main(args.job_id, generate_pfa=False)
    # > compute final --job-id 13
    elif args.mode == 'final':
        main(args.job_id, generate_pfa=True)
