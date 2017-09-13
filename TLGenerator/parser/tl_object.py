import re
from zlib import crc32


class TLObject:
    """.tl core types IDs (such as vector, booleans, etc.)"""
    CORE_TYPES = (
        0xbc799737,  # boolFalse#bc799737 = Bool;
        0x997275b5,  # boolTrue#997275b5 = Bool;
        0x3fedd339,  # true#3fedd339 = True;
        0x1cb5c415,  # vector#1cb5c415 {t:Type} # [ t ] = Vector t;
    )

    def __init__(self, fullname, object_id, args, result, layer, is_function):
        """
        Initializes a new TLObject, given its properties.
        Usually, this will be called from `from_tl` instead
        :param fullname: The fullname of the TL object (namespace.name)
                         The namespace can be omitted
        :param object_id: The hexadecimal string representing the object ID
        :param args: The arguments, if any, of the TL object
        :param result: The result type of the TL object
        :param layer: The layer version of the TL object
        :param is_function: Is the object a function or a type?
        """
        # The name can or not have a namespace
        if '.' in fullname:
            self.namespace = fullname.split('.')[0]
            self.name = fullname.split('.')[1]
        else:
            self.namespace = None
            self.name = fullname

        self.args = args
        self.result = result
        self.layer = layer
        self.is_function = is_function

        # The ID should be an hexadecimal string or None to be inferred
        if object_id is None:
            self.id = self.infer_id()
        else:
            self.id = object_id
            if self.name != "vector":
                assert self.id == self.infer_id(),\
                    'Invalid inferred ID for ' + repr(self)

    @staticmethod
    def from_json(dictionary, is_function):
        """Returns a TL object from the given JSON scheme line"""

        # Retrieve the matched arguments
        args = [TLArg(param['name'], param['type'], False)
                for param in dictionary['params']]

        return TLObject(
            fullname=dictionary['predicate'],
            object_id=int.from_bytes(int(dictionary['id']).to_bytes(4, byteorder='little', signed=True), byteorder='little', signed=False),
            layer=dictionary['layer'],
            args=args,
            result=dictionary['type'],
            is_function=is_function)
        
    @staticmethod
    def from_tl(tl, layer, is_function):
        """Returns a TL object from the given TL scheme line"""

        # Regex to match the whole line
        match = re.match(r'''
            ^                  # We want to match from the beginning to the end
            ([\w.]+)           # The .tl object can contain alpha_name or namespace.alpha_name
            (?:
                \#             # After the name, comes the ID of the object
                ([0-9a-f]+)    # The constructor ID is in hexadecimal form
            )?                 # If no constructor ID was given, CRC32 the 'tl' to determine it

            (?:\s              # After that, we want to match its arguments (name:type)
                {?             # For handling the start of the '{X:Type}' case
                \w+            # The argument name will always be an alpha-only name
                :              # Then comes the separator between name:type
                [\w\d<>#.?!]+  # The type is slightly more complex, since it's alphanumeric and it can
                               # also have Vector<type>, flags:# and flags.0?default, plus :!X as type
                }?             # For handling the end of the '{X:Type}' case
            )*                 # Match 0 or more arguments
            \s                 # Leave a space between the arguments and the equal
            =
            \s                 # Leave another space between the equal and the result
            ([\w\d<>#.?]+)     # The result can again be as complex as any argument type
            ;$                 # Finally, the line should always end with ;
            ''', tl, re.IGNORECASE | re.VERBOSE)

        if match is None:
            # Probably "vector#1cb5c415 {t:Type} # [ t ] = Vector t;"
            raise ValueError('Cannot parse TLObject', tl)

        # Sub-regex to match the arguments (sadly, it cannot be embedded in the first regex)
        args_match = re.findall(r'''
            ({)?             # We may or may not capture the opening brace
            (\w+)            # First we capture any alpha name with length 1 or more
            :                # Which is separated from its type by a colon
            ([\w\d<>#.?!]+)  # The type is slightly more complex, since it's alphanumeric and it can
                             # also have Vector<type>, flags:# and flags.0?default, plus :!X as type
            (})?             # We may or not capture the closing brace
            ''', tl, re.IGNORECASE | re.VERBOSE)

        # Retrieve the matched arguments
        args = [TLArg(name, arg_type, brace != '')
                for brace, name, arg_type, _ in args_match]

        if match.group(2) is None:
            id = None
        else:
            id = int(match.group(2), 16)
        # And initialize the TLObject
        return TLObject(
            fullname=match.group(1),
            object_id=id,
            layer=layer,
            args=args,
            result=match.group(3),
            is_function=is_function)

    def sorted_args(self):
        """Returns the arguments properly sorted and ready to plug-in
           into a Python's method header (i.e., flags and those which
           can be inferred will go last so they can default =None)
        """
        return sorted(self.args,
                      key=lambda x: x.is_flag or x.can_be_inferred)

    def is_core_type(self):
        """Determines whether the TLObject is a "core type"
           (and thus should be embedded in the generated code) or not"""
        return self.id in TLObject.CORE_TYPES

    def __repr__(self, ignore_id=False):
        fullname = ('{}.{}'.format(self.namespace, self.name)
                    if self.namespace is not None else self.name)

        if getattr(self, 'id', None) is None or ignore_id:
            hex_id = ''
        else:
            # Skip 0x and add 0's for padding
            hex_id = '#' + hex(self.id)[2:].rjust(8, '0')

        if self.args:
            args = ' ' + ' '.join([repr(arg) for arg in self.args])
        else:
            args = ''

        return '{}{}{} = {}'.format(fullname, hex_id, args, self.result)

    def infer_id(self):
        representation = self.__repr__(ignore_id=True)

        # Clean the representation
        representation = representation\
            .replace(':bytes ', ':string ')\
            .replace('?bytes ', '?string ')\
            .replace('<', ' ').replace('>', '')\
            .replace('{', '').replace('}', '')\
    

        representation = re.sub(
            r' \w+:flags\.\d+\?true',
            r'',
            representation
        )
        return crc32(representation.encode('ascii'))

    def __str__(self):
        fullname = ('{}.{}'.format(self.namespace, self.name)
                    if self.namespace is not None else self.name)

        # Some arguments are not valid for being represented, such as the flag indicator or generic definition
        # (these have no explicit values until used)
        valid_args = [arg for arg in self.args
                      if not arg.flag_indicator and not arg.generic_definition]

        args = ', '.join(['{}={{}}'.format(arg.name) for arg in valid_args])

        # Since Python's default representation for lists is using repr(), we need to str() manually on every item
        args_format = ', '.join(
            ['str(self.{})'.format(arg.name) if not arg.is_vector else
             'None if not self.{0} else [str(_) for _ in self.{0}]'.format(
                 arg.name) for arg in valid_args])

        return ("'({} (ID: {}) = ({}))'.format({})"
                .format(fullname, hex(self.id), args, args_format))

    @staticmethod
    def get_class_name(tlobject):
        """Gets the class name following the Python style guidelines"""
        # Courtesy of http://stackoverflow.com/a/31531797/4759433
        name = getattr(tlobject, 'name', tlobject)
        result = re.sub(r'_([a-z])', lambda m: m.group(1).upper(), name)
        result = result[:1].upper() + result[1:].replace('_', '')
        return result


class TLArg:
    def __init__(self, name, arg_type, generic_definition):
        """
        Initializes a new .tl argument
        :param name: The name of the .tl argument
        :param arg_type: The type of the .tl argument
        :param generic_definition: Is the argument a generic definition?
                                   (i.e. {X:Type})
        """
        if name == 'self':  # This very only name is restricted
            self.name = 'is_self'
        else:
            self.name = name

        # Default values
        self.is_vector = False
        self.is_flag = False
        self.flag_index = -1

        # Special case: some types can be inferred, which makes it
        # less annoying to type. Currently the only type that can
        # be inferred is if the name is 'random_id', to which a
        # random ID will be assigned if left as None (the default)
        self.can_be_inferred = name == 'random_id'

        # The type can be an indicator that other arguments will be flags
        if arg_type == '#':
            self.flag_indicator = True
            self.type = None
            self.is_generic = False
        else:
            self.flag_indicator = False
            self.is_generic = arg_type.startswith('!')
            self.type = arg_type.lstrip(
                '!')  # Strip the exclamation mark always to have only the name

            # The type may be a flag (flags.IDX?REAL_TYPE)
            # Note that 'flags' is NOT the flags name; this is determined by a previous argument
            # However, we assume that the argument will always be called 'flags'
            flag_match = re.match(r'flags.(\d+)\?([\w<>.]+)', self.type)
            if flag_match:
                self.is_flag = True
                self.flag_index = int(flag_match.group(1))
                # Update the type to match the exact type, not the "flagged" one
                self.type = flag_match.group(2)

            # Then check if the type is a Vector<REAL_TYPE>
            vector_match = re.match(r'vector<(%?)(\w+)>', self.type, re.IGNORECASE)
            if vector_match:
                self.is_vector = True

                # If the type's first letter is not uppercase, then
                # it is a constructor and we use (read/write) its ID
                # as pinpointed on issue #81.
                self.use_vector_id = self.type[0] == 'V'

                # Update the type to match the one inside the vector
                self.type = vector_match.group(2)
                if vector_match.group(1) != '':
                    self.type = vector_match.group(2).lower() # should use a real type lookup here but meh

        self.generic_definition = generic_definition

    def get_type(self, noncore_prefix):
        if self.type == 'int':
            t = 'int32_t'
        elif self.type == 'long':
            t = 'int64_t'
        elif self.type == 'string':
            t = 'std::string'
        elif self.type == 'Bool' or self.type == 'true':
            t = 'bool'
        elif self.type == 'X':
            t = 'Serializable'
        elif self.type == 'bytes':
            t = 'std::vector<uint8_t>'
        elif self.type in {'int', 'long'}:
            t = self.type
        else:
            t = noncore_prefix + self.get_sanitized_result(self.type)

        if self.is_flag:
            t = 'std::optional<{}>'.format(t)

        if self.is_vector:
            t = 'std::vector<{}>'.format(t)

        return t

    @staticmethod
    def get_sanitized_result(result):
        result = result.replace('.', '_')
        if '<' in result:
            result = result[result.find('<')+1:-1]
        return TLObject.get_class_name(result)

    def get_type_name(self, noncore_prefix):
        return '{} {}'.format(self.get_type(noncore_prefix), self.name)

    def __str__(self):
        # Find the real type representation by updating it as required
        real_type = self.type
        if self.flag_indicator:
            real_type = '#'

        if self.is_vector:
            if self.use_vector_id:
                real_type = 'Vector<{}>'.format(real_type)
            else:
                real_type = 'vector<{}>'.format(real_type)

        if self.is_generic:
            real_type = '!{}'.format(real_type)

        if self.is_flag:
            real_type = 'flags.{}?{}'.format(self.flag_index, real_type)

        if self.generic_definition:
            return '{{{}:{}}}'.format(self.name, real_type)
        else:
            return '{}:{}'.format(self.name, real_type)

    def __repr__(self):
        # Get rid of our special type
        return str(self)\
            .replace(':date', ':int')\
            .replace('?date', '?int')\
