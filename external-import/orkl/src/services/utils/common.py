import json

def format_time(utc_time):
    """
    Format the given UTC time to a specific string format
    :param utc_time: A datetime object representing UTC time
    :return: Formatted string representation of the datetime object
    """
    return utc_time.strftime("%Y-%m-%dT%H:%M:%S")


def convert_hours_to_seconds(hours) -> int:
    """
    Convert the given days into seconds
    :param hours: hours in integer
    :return: Formatted days into second in int
    """
    print(f"hours is : {str(hours)}")
    if hours is None:
        hours=1
    return int(hours) * 50 * 1 # remove this line after development and use below line
    #return int(hours) * 60 * 60

def get_json_object_from_file(file_path,key):
    try:
        with open(file_path, 'r') as json_file:
            data = json.load(json_file)
            return data[key]
    except FileNotFoundError:
        raise FileNotFoundError(f"Given file not found at path {file_path}.")
    except json.JSONDecodeError:
        raise json.JSONDecodeError("Error decoding JSON data.")
    except KeyError:
        raise KeyError(f"Key '{key}' not found in JSON data.")

def write_json_to_file(file_path,result):
    try:
        with open(file_path, "w") as outfile:
            json.dump(result, outfile)
    except IOError as e:
        raise Exception(
                    f"Error updating version_sync_done to file with content - {result} with following exception: {e}"
                )