import argparse
import sys
from os import path
sys.path.append(path.expanduser("~/codes/fortpy-dist"))

import fortpy
from fortpy.code import CodeParser
from fortpy import settings

def parse():
    settings.use_filesystem_cache = False
    settings.unit_testing_mode = True

    c = CodeParser()
    
    if args["verbose"]:
        c.verbose = True

    if args["reparse"]:
        c.reparse(args["source"])
    else:
        c.parse(args["source"])

    #Since this is for unit testing, we will access the "private" variables.
    for fname in c._modulefiles:
        for moduledat in c._modulefiles[fname]:
            if args["verbose"]:
                print c.modules[moduledat]
            else:
                print moduledat

#Create a parser so that the script can receive arguments
parser = argparse.ArgumentParser(description="Fortpy File Parsing Unit Testing Tool")

#Add arguments to decide which of the systems and penalties to process.
parser.add_argument("source", help="Specify the path to the source file to parse.")
parser.add_argument("-verbose", help="Sets whether the comparison output is verbose.", action="store_true")
parser.add_argument("-reparse", help="Overwrite the cached version of the module.", action="store_true")

#Parse the args from the commandline that ran the script, call initialize
args = vars(parser.parse_args())
parse()