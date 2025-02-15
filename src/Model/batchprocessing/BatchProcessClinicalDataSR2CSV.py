import csv
import os
from pathlib import Path
from src.Model.batchprocessing.BatchProcess import BatchProcess
from src.Model.PatientDictContainer import PatientDictContainer


class BatchProcessClinicalDataSR2CSV(BatchProcess):
    """
    This class handles batch processing for the Clinical Data 2 CSV
    process. Inherits from the BatchProcessing class.
    """
    # Allowed classes for ClinicalDataSR2CSV
    allowed_classes = {
        # Comprehensive SR
        "1.2.840.10008.5.1.4.1.1.88.33": {
            "name": "sr",
            "sliceable": False
        }
    }

    def __init__(self, progress_callback, interrupt_flag, patient_files,
                 output_path):
        """
        Class initialiser function.
        :param progress_callback: A signal that receives the current
                                  progress of the loading.
        :param interrupt_flag: A threading.Event() object that tells the
                               function to stop loading.
        :param patient_files: List of patient files.
        :param output_path: Path of the output CSV file.
        """
        # Call the parent class
        super(BatchProcessClinicalDataSR2CSV, self).__init__(progress_callback,
                                                             interrupt_flag,
                                                             patient_files)

        # Set class variables
        self.patient_dict_container = PatientDictContainer()
        self.required_classes = ['sr']
        self.ready = self.load_images(patient_files, self.required_classes)
        self.output_path = output_path

    def start(self):
        """
        Goes through the steps of the ClinicalData-SR2CSV conversion.
        :return: True if successful, False if not.
        """
        # Stop loading
        if self.interrupt_flag.is_set():
            self.patient_dict_container.clear()
            self.summary = "INTERRUPT"
            return False

        if not self.ready:
            self.summary = "SKIP"
            return False

        # See if SR contains clinical data
        self.progress_callback.emit(("Checking SR file...", 20))
        cd_sr = self.find_clinical_data_sr()

        if cd_sr is None:
            self.summary = "CD_NO_SR"
            return False

        # Stop loading
        if self.interrupt_flag.is_set():
            self.patient_dict_container.clear()
            self.summary = "INTERRUPT"
            return False

        # Read in clinical data from SR
        self.progress_callback.emit(("Reading clinical data...", 50))
        data_dict = self.read_clinical_data_from_sr(cd_sr)

        # Stop loading
        if self.interrupt_flag.is_set():
            self.patient_dict_container.clear()
            self.summary = "INTERRUPT"
            return False

        # Write clinical data to CSV
        self.progress_callback.emit(("Writing clinical data to CSV...", 80))
        self.write_to_csv(data_dict)
        return True

    def find_clinical_data_sr(self):
        """
        Searches the patient dict container for any SR files containing
        clinical data. Returns the first SR with clinical data found.
        :return: ds, SR dataset containing clinical data, or None if
                 nothing found.
        """
        datasets = self.patient_dict_container.dataset

        for ds in datasets:
            # Check for SR files
            if datasets[ds].SOPClassUID == '1.2.840.10008.5.1.4.1.1.88.33':
                # Check to see if it is a clinical data SR
                if datasets[ds].SeriesDescription == "CLINICAL-DATA":
                    return datasets[ds]

        return None

    def read_clinical_data_from_sr(self, sr_cd):
        """
        Reads clinical data from the found SR file.
        :param sr_cd: the clinical data SR dataset.
        :return: dictionary of clinical data, where keys are attributes
                 and values are data.
        """
        data = sr_cd.ContentSequence[0].TextValue

        data_dict = {}

        data_list = data.split("\n")
        for row in range(len(data_list)):
            if data_list[row] == '':
                continue
            # Assumes neither data nor attributes have colons
            row_data = data_list[row].split(":")
            data_dict[row_data[0]] = row_data[1][1:]

        return data_dict

    def write_to_csv(self, data_dict):
        """
        Append data to the clinical data CSV file. Create it if it
        doesn't exist. Assumes that all data dicts have the same keys
        in the same order and that SR files were generated by OnkODICOM.
        Data will still write, but be jumbled if this is not the case.
        It is recommended that functionality to make data writing
        consistent is implemented in the future, however this requires
        that SR files generated by OnkoDICOM are made to be far more
        structured than they currently are.
        :param data_dict: dictionary of clinical data, where keys are
                          attributes and values are data.
        """
        attribs = []
        values = []

        # Put keys and values into separate lists
        for attrib in data_dict:
            attribs.append(attrib)
            values.append(data_dict[attrib])

        # File path
        path = Path(self.output_path).joinpath("ClinicalData.csv")

        # Set whether we need to write the header or not
        write_header = False
        if not os.path.exists(path):
            write_header = True

        # Write to CSV
        with open(path, 'a', newline="") as stream:
            writer = csv.writer(stream)
            if write_header:
                writer.writerow(attribs)
            writer.writerow(values)
