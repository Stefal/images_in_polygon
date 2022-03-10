#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# summary TODO

import os, sys, datetime
import argparse
import shutil
import json
from dateutil.tz import tzlocal
from lib.exif_read import ExifRead as EXIF
from lib.exif_write import ExifEdit
from shapely.geometry import Point, GeometryCollection, shape


def list_images(directory):
    """
    Create a list of image tuples sorted by capture timestamp.
    @param directory: directory with JPEG files
    @return: a list of image tuples with time, directory, lat,long...
    """
    file_list = []
    for root, sub_folders, files in os.walk(directory):
        file_list += [
            os.path.join(root, filename)
            for filename in files
            if filename.lower().endswith(".jpg")
        ]

    files = []
    # get DateTimeOriginal data from the images and sort the list by timestamp
    for filepath in file_list:
        metadata = EXIF(filepath)
        # metadata.read()
        try:
            t = metadata.extract_capture_time()
            geo = metadata.extract_geo()
            files.append((filepath, t, Point(geo["longitude"], geo["latitude"])))

        except KeyError as e:
            # if any of the required tags are not set the image is not added to the list
            print("Skipping {0}: - {1} is missing".format(filepath, e))

    files.sort(key=lambda timestamp: timestamp[1])
    # print_list(files)
    return files


def import_geojson(geojson_file, properties_key):
    """
    import the geojson file and create a dict with the commune's name as the key
    and a shape object as the value
    """
    with open(geojson_file) as f:
        features = json.load(f)["features"]
    GeometryCollection([shape(feature["geometry"]).buffer(0) for feature in features])
    areas = {}
    for feature in features:
        area_name = feature["properties"][properties_key]
        area_shape = shape(feature["geometry"])
        areas[area_name] = area_shape

    return areas


def check_point_in_polygon(point, area_shape):

    return area_shape.contains(point)


def find_polygon(point, area_shapes, first_check=None):
    """
    find outer polygon for each image (store the previous correct polygon to speed up calculation
     time as the next image will probably be in the same one)
    """
    if first_check is not None:
        if check_point_in_polygon(point, area_shapes[first_check]):
            return first_check

    for area in area_shapes:
        if check_point_in_polygon(point, area_shapes[area]):
            return area

def write_exif(image_path, value):
    #add_custom_tag(self, value, main_key, tag_key)
    #self._ef[main_key][tag_key] = value
    #self._ef["IPTC"]["City"] = city
    metadata = ExifEdit(image_path)
    metadata.add_gpsareainformation(str(value))
    metadata.write()

def file_to_destination(image_path, source_directory, destination_directory, move=False):
    """
    Copy/move image to the destination directory, keeping the subfolder path
    """
    relative_path = os.path.relpath(image_path, source_directory)
    full_destination_path = os.path.join(destination_directory, relative_path)
    os.makedirs(
        os.path.join(destination_directory, os.path.dirname(relative_path)),
        exist_ok=True,
    )
    if os.path.abspath(image_path) == os.path.abspath(full_destination_path):
        # source and destination are identical
        pass
    elif move == True:
        shutil.move(image_path, full_destination_path)
    elif move == False:
        shutil.copy2(image_path, full_destination_path)

    return full_destination_path


def arg_parse():
    """Parse the command line
    options  :
    json_file, source, destination
    """
    parser = argparse.ArgumentParser(
        description="Script to find in which polygon a geolocalized image belongs to"
    )
    parser.add_argument(
        "-j", "--json_file", help="Path to the geojson file", required=True
    )
    parser.add_argument(
        "-p",
        "--properties",
        help="Geojson properties key used to name the subfolders",
        required=True,
    )
    parser.add_argument(
        "-s",
        "--source",
        help="Path to the images folder. Sub folder are scanned too",
        required=True,
    )
    parser.add_argument(
        "-a",
        "--copy_orphan",
        help="Copy images located outside of any polygon to the destination/no_area directory",
        action="store_true",
        default=False
    )
    parser.add_argument(
        "-d",
        "--destination",
        help="Path to the destination folder in which the images will be copied",
    )
    parser.add_argument(
        "-m",
        "--move",
        help="Move files to destination instead of copy files",
        action="store_true",
    )
    parser.add_argument(
        "-w",
        "--write_tag",
        help="write area name inside image exif metadata (GpsAreaInformation)",
        action="store_true",
        default=False
    )
    parser.add_argument(
        "-q",
        "--quiet",
        help="Don't display images results",
        action="store_true",
    )
    parser.add_argument("-v", "--version", action="version", version="release 1.2")

    args = parser.parse_args()
    return args


def main():
    print("image source path is:", args.source)
    print("importing geojson: ", args.json_file, end=" - ")
    area_dict = import_geojson(args.json_file, args.properties)
    print("{} polygons loaded".format(len(area_dict)))
    # create image list with point position for shapely
    print("creating image list...", end=" ")
    images_list = list_images(args.source)
    print("{} images found".format(len(images_list)))
    # find outer polygon for each image
    print("searching for city...")
    previous_area = None
    image_count = 0
    used_area = {}
    for image in images_list:
        area = find_polygon(image[2], area_dict, previous_area)
        if not area and not args.copy_orphan:
            #image outside of polygons and copy orphan is False
            continue
        used_area[area] = used_area.get(area, 0) + 1
        if area is not None:
            previous_area = area
        if args.destination:
            # copy/move images to a new directory named with the city name
            if area is not None:
                dest_folder_name = os.path.join("..", area, "intérieur")
            else:
                dest_folder_name = os.path.join(args.destination, "extérieur")
            new_path = file_to_destination(
                image[0], args.source, os.path.join(args.destination, dest_folder_name), args.move)
            image_count += 1
            if args.write_tag and area is not None:
                write_exif(new_path, area)
        if not args.quiet:
            #print("{} -> {}".format(image[0], area))
            print("{} -> {}".format(image[0], new_path))

    print("{} images {} to {} directory : {}".format(image_count, "copied" if args.move == False else "moved", len(used_area), used_area))
    print("End of Script")


if __name__ == "__main__":
    # Parsing the command line arguments
    args = arg_parse()
    print(args)
    main()