import re
import json
from .tl_object import TLObject


class TLParser:
    """Class used to parse .tl files"""

    @staticmethod
    def parse_files(schemes, ignore_core=False):
        """This method yields TLObjects from a given .tl file"""
        for layer, file_path in schemes.items():

            with open(file_path, encoding='utf-8') as file:
                try:
                    jdata = json.load(file)
                    for constructor in jdata['constructors']:
                        if 'layer' not in constructor:
                            constructor['layer'] = layer
                        result = TLObject.from_json(constructor, is_function=False)
                        if not ignore_core or not result.is_core_type():
                            yield result

                    for method in jdata['methods']:
                        method['predicate'] = method['method']
                        if 'layer' not in method:
                            method['layer'] = layer

                        result = TLObject.from_json(method, is_function=True)
                        if not ignore_core or not result.is_core_type():
                            yield result
                        
                except json.decoder.JSONDecodeError:
                    file.seek(0)

                    # Start by assuming that the next found line won't
                    # be a function (and will hence be a type)
                    is_function = False

                    # Read all the lines from the .tl file
                    for line in file:
                        line = line.strip()

                        # Ensure that the line is not a comment
                        if line and not line.startswith('//'):

                            # Check whether the line is a type change
                            # (types <-> functions) or not
                            match = re.match('---(\w+)---', line)
                            if match:
                                is_function = match.group(1) == 'functions'
                                continue

                            match = re.search('^===(\d+)===$', line)
                            if match:
                                layer = match.group(1)
                                continue

                            try:
                                result = TLObject.from_tl(line, layer=layer, is_function=is_function)
                                if not ignore_core or not result.is_core_type():
                                    yield result
                            except ValueError as e:
                                if 'vector#1cb5c415' not in str(e):
                                    raise
