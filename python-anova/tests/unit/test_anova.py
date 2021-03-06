import pytest
import mock
import json
import os
from anova import generate_formula, main
from mip_helper import errors
from mip_helper import testing as t


def test_generate_formula():
    """Raise error when factorial design and too many covariables are used."""
    dep_var = {'name': 'dep'}
    indep_vars = [{'name': str(i)} for i in range(10)]
    with pytest.raises(errors.UserError):
        generate_formula(dep_var, indep_vars, 'factorial')


@mock.patch('anova.io_helper.fetch_data')
@mock.patch('anova.io_helper.save_results')
def test_main(mock_save_results, mock_fetch_data):
    mock_fetch_data.return_value = t.inputs_regression(include_nominal=False)
    main()
    result = json.loads(mock_save_results.call_args[0][0])
    assert t.round_dict(result) == {
        'Residual': {
            'F': 'NaN',
            'PR(>F)': 'NaN',
            'df': 1.0,
            'mean_sq': 0.019,
            'sum_sq': 0.019
        },
        'minimentalstate': {
            'F': 12.831,
            'PR(>F)': 0.173,
            'df': 1.0,
            'mean_sq': 0.248,
            'sum_sq': 0.248
        },
        'subjectage': {
            'F': 0.958,
            'PR(>F)': 0.507,
            'df': 1.0,
            'mean_sq': 0.019,
            'sum_sq': 0.019
        },
        'subjectage:minimentalstate': {
            'F': 0.096,
            'PR(>F)': 0.808,
            'df': 1.0,
            'mean_sq': 0.002,
            'sum_sq': 0.002
        }
    }


@mock.patch('anova.io_helper.fetch_data')
@mock.patch('anova.io_helper.save_error')
@mock.patch('sys.exit')
def test_main_signular_matrix(mock_exit, mock_save_error, mock_fetch_data):
    mock_fetch_data.return_value = t.inputs_regression(limit_to=1, include_nominal=False)
    main()
    mock_save_error.assert_called_with('Too many factors (4) for too little data (1). Use less covariables or different design.')


@mock.patch('anova.io_helper.fetch_data')
@mock.patch('anova.io_helper.save_error')
@mock.patch('sys.exit')
def test_main_empty_input(mock_exit, mock_save_error, mock_fetch_data):
    mock_fetch_data.return_value = t.inputs_regression(limit_to=0)
    main()

    mock_exit.assert_called_once_with(1)
    mock_save_error.assert_called_once()

@mock.patch('anova.io_helper.save_results')
def test_main_my_data(mock_save_results):
    os.environ['INPUT_FILE'] = 'tests/unit/data.csv'
    os.environ['PARAM_variables'] = 'a'
    os.environ['PARAM_covariables'] = 'b,c'
    os.environ['PARAM_meta'] = "{\"a\":{\"description\":\"\",\"code\":\"a\",\"type\":\"real\"},\"b\":{\"description\":\"\",\"code\":\"b\",\"type\":\"real\"},\"c\":{\"description\":\"\",\"code\":\"c\",\"type\":\"real\"}}"
    main()
    result = json.loads(mock_save_results.call_args[0][0])
    # assert result ...