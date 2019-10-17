import glob
import os
import re
import numpy as np
from PyQt5.QtCore import QFileInfo
from dicompylercore import dvhcalc, dvh, dicomparser
import pydicom
import collections
from PyQt5 import QtCore
from src.Model.ROI import *
import multiprocessing


class Extended(QtCore.QThread):
    """
    For running copy operation
    """

    copied_percent_signal = QtCore.pyqtSignal(int)
    incorrect_directory_signal = QtCore.pyqtSignal()
    missing_files_signal = QtCore.pyqtSignal(str)

    def __init__(self, path):
        super().__init__()
        self.copied = 0
        self.file_size = QFileInfo(path).size()
        self.path = path
        self.read_data_dict = {}

        # Data contains file paths
        # Key is int for ct images and str (rtdose, rtss, rtplan) for RT files
        self.file_names_dict = {}
        self.previous = 0

    def run(self):
        self.dataset, self.file_names_dict = self.get_datasets(
            self.path, self.my_callback)

        if not self.file_names_dict:
            self.incorrect_directory_signal.emit()

        elif 'rtss' not in self.file_names_dict:
            if 'rtdose' not in self.file_names_dict:
                self.missing_files_signal.emit(
                    'RTStruct and RTDose files not found in selected directory')
            else:
                self.missing_files_signal.emit(
                    'RTStruct file not found in selected directory')
        else:
            self.file_rtss = self.file_names_dict['rtss']
            self.file_rtdose = self.file_names_dict['rtdose']
            self.dataset_rtss = pydicom.dcmread(self.file_rtss, force=True, defer_size=100)
            self.dataset_rtdose = pydicom.dcmread(self.file_rtdose, force=True, defer_size=100)
            self.rois = self.get_roi_info(self.dataset_rtss, self.my_callback)
            self.raw_dvh = self.calc_dvhs(
                self.dataset_rtss, self.dataset_rtdose, self.rois, self.my_callback)
            self.dvh_x_y = self.converge_to_O_dvh(
                self.raw_dvh, self.my_callback)
            self.dict_raw_ContourData, self.dict_NumPoints = self.get_raw_ContourData(
                self.dataset_rtss)
            self.dict_pixluts = self.get_pixluts(self.dataset)

            if self.previous < 100:
                for i in range(self.previous, 101):
                    self.copied_percent_signal.emit(int(i))

    def my_callback(self, temp_file_size):
        percent = int(temp_file_size/self.file_size*10)
        if percent < self.previous or percent == 100:
            percent = self.previous
        elif percent == self.previous and percent < 98:
            percent += 1
        elif percent == self.previous:
            percent += 1

        self.copied_percent_signal.emit(percent)
        print("here", percent)
        self.previous = percent

    def natural_sort(self, file_list):
        # Logger info
        def convert(text): return int(text) if text.isdigit() else text.lower()
        def alphanum_key(key): return [convert(c)
                                       for c in re.split('([0-9]+)', key)]
        return sorted(file_list, key=alphanum_key)

    def get_datasets(self, path, callback):
        """
        :param path: str
        :return read_data_dict: dict
        :return file_names_dict: dict
        """

        # Data contains data read from files
        # Key is int for ct images and str (rtdose, rtss, rtplan) for RT files
        self.read_data_dict = {}

        # Data contains file paths
        # Key is int for ct images and str (rtdose, rtss, rtplan) for RT files
        self.file_names_dict = {}

        # Sort files based on name
        dcm_files = self.natural_sort(glob.glob(path + '/*'))
        i = 0  # For key values for ct images

        # For each file in path
        for file in dcm_files:
            try:
                read_file = pydicom.dcmread(file, force=True)
            except:
                pass
            else:
                if read_file.Modality == 'CT':
                    self.read_data_dict[i] = read_file
                    self.file_names_dict[i] = file
                    i += 1
                elif read_file.Modality == 'RTSTRUCT':
                    self.read_data_dict['rtss'] = read_file
                    self.file_names_dict['rtss'] = file
                elif read_file.Modality == 'RTDOSE':
                    self.read_data_dict['rtdose'] = read_file
                    self.file_names_dict['rtdose'] = file
                elif read_file.Modality == 'RTPLAN':
                    self.read_data_dict['rtplan'] = read_file
                    self.file_names_dict['rtplan'] = file
                self.copied += len(read_file)
                callback(self.copied)

        return self.read_data_dict, self.file_names_dict

    def get_roi_info(self, ds_rtss, callback):
        dict_roi = {}
        for sequence in ds_rtss.StructureSetROISequence:
            dict_temp = {}
            dict_temp['uid'] = sequence.ReferencedFrameOfReferenceUID
            dict_temp['name'] = sequence.ROIName
            dict_temp['algorithm'] = sequence.ROIGenerationAlgorithm
            dict_roi[sequence.ROINumber] = dict_temp
            self.copied += len(dict_roi[sequence.ROINumber])
            callback(self.copied)
        return dict_roi

    # Multiprocessing dvh
    def multi_get_dvhs(self, rtss, dose, roi, queue, callback, dose_limit=None):
        dvh = {}
        dvh[roi] = dvhcalc.get_dvh(rtss, dose, roi, dose_limit)

        self.copied += roi
        callback(self.copied)
        print(self.copied)
        print("This is", roi)
        queue.put(dvh)

    # Return a dictionary of all the DVHs of all the ROIs of the patient
    # Return value: dict
    # {"1": dvh}
    # "1" is the ID of the ROI
    # dvh is a data type defined in dicompyler-core
    # For dvh plotting example with matplotlib, see: dvh_plot()
    def calc_dvhs(self, rtss, rtdose, dict_roi, callback, dose_limit=None):
        queue = multiprocessing.Queue()
        processes = []
        dict_dvh = {}

        roi_list = []
        for key in dict_roi:
            roi_list.append(key)
            self.copied += len(roi_list)
            callback(self.copied)

        for i in range(len(roi_list)):
            p = multiprocessing.Process(target=self.multi_get_dvhs, args=(
                rtss, rtdose, roi_list[i], queue, callback))
            processes.append(p)
            self.copied += len(processes)
            callback(self.copied)
            p.start()

        for proc in processes:
            dvh = queue.get()
            dict_dvh.update(dvh)
        self.copied += len(processes)
        callback(self.copied)

        for proc in processes:
            proc.join()
        self.copied += len(processes)
        callback(self.copied)

        return dict_dvh

    # Deal with the case where the last value of the DVH is not 0
    # Return a dictionary of bincenters (x axis of DVH) and counts (y value of DVH)
    # Return value: dict
    # {"1": {"bincenters": bincenters ; "counts": counts}}
    # "1" is the ID of the ROI

    def converge_to_O_dvh(self, dict_dvh, callback):
        res = {}
        zeros = np.zeros(3)
        for roi in dict_dvh:
            res[roi] = {}
            dvh = dict_dvh[roi]

            # The last value of DVH is not equal to 0
            if dvh.counts[-1] != 0:
                tmp_bincenters = []
                for i in range(3):
                    tmp_bincenters.append(dvh.bincenters[-1]+i)

                tmp_bincenters = np.array(tmp_bincenters)
                tmp_bincenters = np.concatenate(
                    (dvh.bincenters.flatten(), tmp_bincenters))
                bincenters = np.array(tmp_bincenters)
                counts = np.concatenate(
                    (dvh.counts.flatten(), np.array(zeros)))

            # The last value of DVH is equal to 0
            else:
                bincenters = dvh.bincenters
                counts = dvh.counts

            res[roi]['bincenters'] = bincenters
            res[roi]['counts'] = counts
        self.copied += len(res)
        callback(self.copied)
        return res

    # Get raw contour data of ROI in RT Structure Set

    def get_raw_ContourData(self, rtss):
        # Retrieve a dictionary of ROIName & ROINumber pairs
        dict_id = {}
        for i, elem in enumerate(rtss.StructureSetROISequence):
            roi_number = elem.ROINumber
            roi_name = elem.ROIName
            dict_id[roi_number] = roi_name

        dict_ROI = {}
        dict_NumPoints = {}
        for roi in rtss.ROIContourSequence:
            ROIDisplayColor = roi.ROIDisplayColor
            ReferencedROINumber = roi.ReferencedROINumber
            ROIName = dict_id[ReferencedROINumber]
            dict_contour = collections.defaultdict(list)
            roi_points_count = 0
            for slice in roi.ContourSequence:
                for contour_img in slice.ContourImageSequence:
                    ReferencedSOPInstanceUID = contour_img.ReferencedSOPInstanceUID
                ContourGeometricType = slice.ContourGeometricType
                NumberOfContourPoints = slice.NumberOfContourPoints
                roi_points_count += int(NumberOfContourPoints)
                ContourData = slice.ContourData
                dict_contour[ReferencedSOPInstanceUID].append(ContourData)
            dict_ROI[ROIName] = dict_contour
            dict_NumPoints[ROIName] = roi_points_count
        return dict_ROI, dict_NumPoints

    def calculate_matrix(self, img_ds):
        # Physical distance (in mm) between the center of each image pixel, specified by a numeric pair
        # - adjacent row spacing (delimiter) adjacent column spacing.
        dist_row = img_ds.PixelSpacing[0]
        dist_col = img_ds.PixelSpacing[1]
        # The direction cosines of the first row and the first column with respect to the patient.
        # 6 values inside: [Xx, Xy, Xz, Yx, Yy, Yz]
        orientation = img_ds.ImageOrientationPatient
        # The x, y, and z coordinates of the upper left hand corner
        # (center of the first voxel transmitted) of the image, in mm.
        # 3 values: [Sx, Sy, Sz]
        position = img_ds.ImagePositionPatient

        # Equation C.7.6.2.1-1.
        # https://dicom.innolitics.com/ciods/rt-structure-set/roi-contour/30060039/30060040/30060050
        matrix_M = np.matrix(
            [[orientation[0] * dist_row, orientation[3] * dist_col, 0, position[0]],
             [orientation[1] * dist_row, orientation[4] * dist_col, 0, position[1]],
             [orientation[2] * dist_row, orientation[5] * dist_col, 0, position[2]],
             [0, 0, 0, 1]]
        )
        x = []
        y = []
        for i in range(0, img_ds.Columns):
            i_mat = matrix_M * np.matrix([[i], [0], [0], [1]])
            x.append(float(i_mat[0]))

        for j in range(0, img_ds.Rows):
            j_mat = matrix_M * np.matrix([[0], [j], [0], [1]])
            y.append(float(j_mat[1]))

        return (np.array(x), np.array(y))

    def get_pixluts(self, dict_ds):
        dict_pixluts = {}
        non_img_type = ['rtdose', 'rtplan', 'rtss']
        for ds in dict_ds:
            if ds not in non_img_type:
                img_ds = dict_ds[ds]
                pixlut = calculate_matrix(img_ds)
                dict_pixluts[img_ds.SOPInstanceUID] = pixlut
        return dict_pixluts
