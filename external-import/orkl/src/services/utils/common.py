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
    return int(hours) * 50 * 1 # remove this line after development and use below line
    #return int(hours) * 60 * 60

def read_json_from_file(file_path):
    try:
        with open(file_path, 'r') as json_file:
            data = json.load(json_file)
            return data["version_sync_done"]
    except FileNotFoundError:
        raise FileNotFoundError("Sync details file not found.")
    except json.JSONDecodeError:
        raise json.JSONDecodeError("Error decoding JSON data.")
    except KeyError:
        raise KeyError("Key 'version_sync_done' not found in JSON data.")