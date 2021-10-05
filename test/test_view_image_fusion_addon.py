"""
Created: 3/10/2021
"""

import pytest
import json

from random import randint, random

from src.Controller.GUIController import MainWindow
from src.View.addons.ImageFusionAddOnOption import *


class TestObject:
    """
    Create a test object that can be used to load in data from the data folder
    """
    def __init__(self):
        self.dict = {}
        self.json_object = None
        self.generate_dict_data()
        self.convert_dict_to_json()

        # Open the main window
        self.main_window = MainWindow()
        self.main_window.show()

        self.window = self.main_window.add_on_options_controller.window
        self.add_on_window = ImageFusionOptions(self.window)

    def get_json(self):
        return self.json_object

    def get_dict(self):
        return self.dict

    def generate_dict_data(self):
        self.dict["reg_method"] = "rigid"
        self.dict["metric"] = "mean_squares"
        self.dict["optimiser"] = "gradient_descent"
        self.dict["shrink_factors"] = randint(1, 10)
        self.dict["smooth_sigmas"] = randint(1, 10)
        self.dict["sampling_rate"] = random()
        self.dict["final_interp"] = randint(1, 10)
        self.dict["number_of_iterations"] = randint(1, 100)
        self.dict["default_number"] = randint(-1000, 1000)

    def convert_dict_to_json(self):
        self.json_object = json.dumps(self.dict)


@pytest.fixture(scope="module")
def test_object():
    """
    Function to pass a shared TestObject object to each test.
    """
    test = TestObject()
    return test


def test_dict_setting_values(test_object):

    dummy_UI = test_object.add_on_window()

    for key in test_object.dict:
        dummy_UI.set_value(key, test_object.dict[key])

    assert dummy_UI.dict == test_object.dict