#!/usr/bin/env python3

import shutil
import numpy as np
import re, os, glob
import skimage
from matplotlib import pyplot as plt
import numpy as np
from pathlib import Path

from weaviate_client import WeaviateClient
import tensorflow as tf
from msirs_utils.segmentation.senet_model import SENet
import argparse
import json

IMAGE_THRESHOLD_CERT = 11
ROI_THRESHOLD_CERT_LOW = 5
ROI_THRESHOLD_CERT_HIGH = 10
CERT_THRESHOLD = 8

HOME = str(Path.home())

CATEGORIES = {
    0: "aec",
    1: "ael",
    2: "cli",
    3: "cra",
    4: "fse",
    5: "fsf",
    6: "fsg",
    7: "fss",
    8: "mix",
    9: "rid",
    10: "rou",
    11: "sfe",
    12: "sfx",
    13: "smo",
    14: "tex",
}


color_info = {
    "aec": (31, 119, 180),
    "ael": (174, 199, 232),
    "cli": (255, 127, 14),
    "rid": (197, 176, 213),
    "fsf": (152, 223, 138),  # DONE
    "sfe": (196, 156, 148),
    "fsg": (214, 39, 40),
    "fse": (44, 160, 44),
    "fss": (255, 152, 150),
    "cra": (255, 187, 120),
    "sfx": (227, 119, 194),  # DONE
    "mix": (148, 103, 189),
    "rou": (140, 86, 74),  # DONE
    "smo": (247, 182, 210),
    "tex": (127, 127, 127),  # DONE
}


interesting_classes = [
    color_info["cra"],
    color_info["aec"],
    color_info["ael"],
    color_info["cli"],
    color_info["rid"],
    color_info["fsf"],
]

# TODO: add path here as constant
MODEL_PATH = ""


class PipelineV3:
    def __init__(
        self,
        db_adr: str,
        schema: str = "Test",
        model_path=None,
        image_storage_directory: str = "/images/",
    ):
        self.client = WeaviateClient(db_adr, schema)
        self.image_storage_directory = image_storage_directory
        print("Num GPUs Available: ", len(tf.config.list_physical_devices("GPU")))

        if model_path == None:
            model_path = MODEL_PATH

        self.model = SENet(model_path=model_path)

    def query_image(self, img: np.ndarray) -> dict:
        try:
            vector = self.model.get_descriptor(img)
            response = self.client.query_image(vector)
            return response
        except Exception as e:
            print(f"Error: {e}")
            return {"has_error": True}

    def build_database(self, directory: str, allowed_formats=["jpg", "png"]) -> bool:
        excep = False
        img_files = []
        if directory[-1] != "/":
            directory += "/"
        for format in allowed_formats:
            img_files.append(glob.glob(f"{directory}+**/*.{format}", recursive=True))
        for img_file in img_files:
            try:
                self.add_to_db(img_file)
            except Exception as e:
                print(f"Skipping {img_file}: {e}")
                excep = True

        return excep

    def get_certainty(self) -> None:
        # TODO: is this needed?
        pass

    def store_for_ui(self, folder: str, results: dict, query: str) -> bool:
        # TODO: this needs refactoring
        print(results)
        excep = False
        images_path = HOME + "/segmentation/segmented/"
        for filename in os.listdir(folder):
            file_path = os.path.join(folder, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f"Failed to delete {file_path}. Reason: {e}")
                excep = True

        # TODO: add query image in this folder as well
        # TODO: handle the metadata extraction and persisting here!!
        print(query)
        file_format = query.split(".")[-1]
        print(file_format)
        shutil.copy(query, folder + f"query.{file_format}")
        counter = 1
        images = results["source"]
        meta_data = results["meta_data"]
        distances = results["distances"]
        for result in images:
            all_imgs = glob.glob(
                HOME + "/codebase-v1/data/data/" + "/**/**/*.jpg", recursive=True
            )
            img_name = result[0].split("/")[-1]
            img = [i for i in all_imgs if re.findall(img_name, i)][0]
            cutout = skimage.io.imread(img)
            skimage.io.imsave(folder + f"retrieval_{counter}.png", cutout)
            counter += 1

        meta_data_dict = {}
        for idx in range(len(meta_data)):
            meta_data_dict["meta_data"] = meta_data[idx]
            meta_data_dict["distances"] = distances[idx]

        with open(folder + "metadata.json", "w+") as f:
            json.dump(meta_data_dict, f)

        return excep

    def add_to_db(self, img_path: str):
        """
        Provided an image path, this function adds the image into the assoicated weaviate database.
        """
        img = skimage.io.imread(img_path)
        new_image_file_name = self.image_storage_directory + img_path.split("/")[-1]
        skimage.io.imsave(new_image_file_name, img)
        self.client.add_to_db(
            img, original_file_path=img_path, file_path=new_image_file_name
        )

    def do_retrieval(self, img_path: str):
        # this executes all methods for the retrieval process
        img = skimage.io.imread(img_path)
        response = self.query_image(img)
        if "has_error" in list(response.keys()):
            print("Error in during query")
            return Exception
        else:
            self.store_for_ui(HOME + "/server-test/", response, img_path)
            self.clear_queue()

    def add_uploaded_image(self, img: str):
        # TODO: this needs to be fit to the metadata handling
        # TODO: check for security here??
        self.add_to_db(img)
        # TODO: handle metadata here
        pass

    def add_segmented_img(self, img: str) -> bool:
        return True

    @staticmethod
    def format_image(img: np.ndarray) -> np.ndarray:
        # TODO: do i need that? i have something like this in the senet_model file,,,
        return np.zeros((3, 3))

    @staticmethod
    def clear_queue() -> bool:
        # TODO: needs refactor after changes to store_for_ui()
        excep = False
        folder = HOME + "/query/"
        for filename in os.listdir(folder):
            file_path = os.path.join(folder, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f"Failed to delete {file_path}. Reason: {e}")
                excep = True
        return excep


if __name__ == "__main__":
    pipe = PipelineV3("http://localhost:8080")

    parser = argparse.ArgumentParser(
        description="Script to allow interaction with MSIRS."
    )
    parser.add_argument(
        "-r",
        "--retrieve",
        type=pipe.do_retrieval,
        action="store",
        help="Retrieve images for image corresponding to provided path",
    )
    parser.add_argument(
        "-a",
        "--add",
        help="Add image provided per path into the database",
        type=pipe.add_uploaded_image,
        action="store",
    )
    parser.add_argument(
        "-p",
        "--populate",
        type=pipe.build_database,
        action="store",
        help="Populate database by adding all provided images",
    )
    parser.add_argument(
        "--summary",
        type=pipe.client.check_db,
        help="Print summary of the current database state",
    )
