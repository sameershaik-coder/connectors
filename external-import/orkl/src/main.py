"""OpenCTI CVE connector main module"""

import time

from connector import CPEConnector

if __name__ == "__main__":
    """
    Entry point of the script5
    """
    try:
        connector = CPEConnector()
        connector.run()
    except Exception as err:
        print(err)
        time.sleep(10)
        exit(0)
