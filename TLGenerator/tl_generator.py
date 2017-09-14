import os
import re
import shutil
from zlib import crc32
from collections import defaultdict

from parser import SourceBuilder, TLParser
from parser.tl_object import TLObject, TLArg
AUTO_GEN_NOTICE = \
    '// File generated by TLObjects\' generator. All changes will be ERASED'


class TLGenerator:
    def __init__(self, output_dir):
        self.output_dir = output_dir

    def _get_file(self, *paths):
        return os.path.join(self.output_dir, *paths)

    def _rm_if_exists(self, filename):
        file = self._get_file(filename)
        if os.path.exists(file):
            if os.path.isdir(file):
                shutil.rmtree(file)
            else:
                os.remove(file)

    def clean_tlobjects(self):
        for name in ('functions.cpp', 'types.cpp'):
            self._rm_if_exists(name)

    def generate_tlobjects(self, scheme_files):
        os.makedirs(self.output_dir, exist_ok=True)

        tlobjects = tuple(TLParser.parse_files(scheme_files, ignore_core=True))

        layer_functions = defaultdict(lambda: defaultdict(list))
        layer_types = defaultdict(lambda: defaultdict(list))
        function_abstracts = defaultdict(set)
        object_abstracts = defaultdict(set)

        for tlobject in tlobjects:
            tlobject.result = TLArg.get_sanitized_result(tlobject.result)

            if tlobject.is_function:
                layer_functions[tlobject.layer][tlobject.namespace].append(tlobject)
                function_abstracts[tlobject.layer].add(tlobject.result)
            else:
                layer_types[tlobject.layer][tlobject.namespace].append(tlobject)
                object_abstracts[tlobject.layer].add(tlobject.result)

        self._generate_source(self._get_file('functions.cpp'), layer_functions, function_abstracts)
        self._generate_source(self._get_file('types.cpp'), layer_types, object_abstracts)

    @staticmethod
    def _generate_source(file, layer_tlobjects, layer_abstracts):
        # layer_tlobjects: {'namespace', [TLObject]}
        with open(file, 'w', encoding='utf-8') as f, SourceBuilder(f) as builder:
            builder.writeln(AUTO_GEN_NOTICE)
            builder.writeln('#include <optional>')
            builder.writeln('#include <string>')
            builder.writeln('#include <vector>')
            builder.writeln('#include <stdint.h>')
            builder.writeln('#include "../stream.cpp"')
            builder.writeln()
            builder.writeln('namespace TL {')

            builder.writeln('namespace Type {')
            for layer, abstracts in layer_abstracts.items():
                builder.writeln('namespace L{} {{'.format(layer))
                for a in sorted(abstracts):
                    builder.writeln('class {} : public Serializable {{ }};'.format(a))
                builder.end_block()

            builder.end_block()

            for layer, namespace_tlobjects in layer_tlobjects.items():
                builder.writeln('namespace L{} {{'.format(layer))
                for ns, tlobjects in namespace_tlobjects.items():
                    if ns:
                        builder.writeln('namespace {} {{'.format(ns))

                    # Generate the class for every TLObject
                    for t in sorted(tlobjects, key=lambda x: x.name):
                        TLGenerator._write_source_code(t, builder)

                    if ns:
                        builder.end_block()
                builder.end_block()

            builder.end_block()


    @staticmethod
    def _write_source_code(tlobject, builder):
        class_name = TLObject.get_class_name(tlobject)
        ns_prefix = 'TL::Type::L{}::'.format(tlobject.layer)

        builder.writeln('class {} : public {}{} {{'.format(
            class_name, ns_prefix, tlobject.result
        ))
        builder.current_indent -= 1
        builder.writeln('public:')
        builder.current_indent += 1

        builder.writeln('static const uint32_t CONSTRUCTOR = {};'.format(
            hex(tlobject.id)
        ))
        builder.writeln()

        # Flag arguments must go last
        args = [
            a for a in tlobject.sorted_args()
            if not a.flag_indicator and not a.generic_definition
        ]

        for arg in args:
            builder.writeln('{};'.format(arg.get_type_name(ns_prefix)))

        # Write the constructor
        params = [arg.get_type_name(ns_prefix) if not arg.is_flag
                  else '{} = {{}}'.format(arg.get_type_name(ns_prefix)) for arg in args]

        builder.writeln()
        builder.writeln(
            '{}({}) {{'.format(class_name, ', '.join(params))
        )

        for arg in args:
            builder.writeln('this->{} = {};'.format(arg.name, arg.name))

        builder.end_block()

        builder.writeln('void write(const OutputStream& stream) override {')
        builder.writeln('stream << {}::CONSTRUCTOR;'.format(class_name))
        for arg in args:
            if arg.is_vector:
                if arg.use_vector_id:
                    builder.writeln('stream << 0x1cb5c415;')
                builder.writeln('stream << static_cast<uint32_t>({}.size());'.format(arg.name))
                builder.writeln('for (auto const& _x: {}) {{'.format(arg.name))
                builder.writeln('stream << _x;')
                builder.end_block()
            else:
                builder.writeln('stream << {};'.format(arg.name))
        builder.end_block()

        builder.writeln('void read(const OutputStream& stream) override {')
        if any(a for a in args if a.is_vector):
            builder.writeln('uint32_t _len, _i;')
        for arg in args:
            if arg.is_vector:
                if arg.use_vector_id:
                    builder.writeln('stream >> _i;')
                builder.writeln('stream >> _len;')
                builder.writeln('for (_i = 0; i != _len; ++_i) {')
                # TODO Actually read the TLObject
                builder.writeln('/* TODO Actually read the TLObject */')
                builder.end_block()
            else:
                builder.writeln('stream >> {};'.format(arg.name))
        builder.end_block()
        builder.end_block()

if __name__ == '__main__':
    generator = TLGenerator('../Thallium/tl')
    print('Detected previous TLObjects. Cleaning...')
    generator.clean_tlobjects()

    print('Generating TLObjects...')
    generator.generate_tlobjects({1: "schemes/TL_mtproto_v1.json", 71: "schemes/TL_telegram_v71.tl"})

    print('Done.')
