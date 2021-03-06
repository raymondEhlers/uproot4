# BSD 3-Clause License; see https://github.com/scikit-hep/uproot4/blob/master/LICENSE

"""
Utilities for internal use. This is not a public interface and may be changed
without notice.
"""

from __future__ import absolute_import

import os
import sys
import numbers
import re
import glob

try:
    from collections.abc import Iterable
except ImportError:
    from collections import Iterable
try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse

import numpy


py2 = sys.version_info[0] <= 2
py26 = py2 and sys.version_info[1] <= 6
py27 = py2 and not py26
py35 = not py2 and sys.version_info[1] <= 5
win = os.name == "nt"


if py2:
    # to silence flake8 F821 errors
    unicode = eval("unicode")
    range = eval("xrange")
else:
    unicode = None
    range = eval("range")


def isint(x):
    """
    Returns True if and only if `x` is an integer (including NumPy, not
    including bool).
    """
    return isinstance(x, (int, numbers.Integral, numpy.integer)) and not isinstance(
        x, (numpy.bool, numpy.bool_)
    )


def isnum(x):
    """
    Returns True if and only if `x` is a number (including NumPy, not
    including bool).
    """
    return isinstance(x, (int, float, numbers.Real, numpy.number)) and not isinstance(
        x, (numpy.bool, numpy.bool_)
    )


def isstr(x):
    if py2:
        return isinstance(x, (bytes, unicode))
    else:
        return isinstance(x, str)


def ensure_str(x):
    if not py2 and isinstance(x, bytes):
        return x.decode(errors="surrogateescape")
    elif py2 and isinstance(x, unicode):
        return x.encode()
    elif isinstance(x, str):
        return x
    else:
        raise TypeError("expected a string, not {0}".format(type(x)))


_regularize_filter_regex = re.compile("^/(.*)/([iLmsux]*)$")


def _regularize_filter_regex_flags(flags):
    flagsbyte = 0
    for flag in flags:
        if flag == "i":
            flagsbyte += re.I
        elif flag == "L":
            flagsbyte += re.L
        elif flag == "m":
            flagsbyte += re.M
        elif flag == "s":
            flagsbyte += re.S
        elif flag == "u":
            flagsbyte += re.U
        elif flag == "x":
            flagsbyte += re.X
    return flagsbyte


def no_filter(x):
    return True


def regularize_filter(filter):
    if filter is None:
        return no_filter
    elif callable(filter):
        return filter
    elif isstr(filter):
        m = _regularize_filter_regex.match(filter)
        if m is not None:
            regex, flags = m.groups()
            return (
                lambda x: re.match(regex, x, _regularize_filter_regex_flags(flags))
                is not None
            )
        elif "*" in filter or "?" in filter or "[" in filter:
            return lambda x: glob.fnmatch.fnmatchcase(x, filter)
        else:
            return lambda x: x == filter
    elif isinstance(filter, Iterable) and not isinstance(filter, bytes):
        filters = [regularize_filter(f) for f in filter]
        return lambda x: any(f(x) for f in filters)
    else:
        raise TypeError(
            "filter must be callable, a regex string between slashes, or a "
            "glob pattern, not {0}".format(repr(filter))
        )


def regularize_path(path):
    if isinstance(path, getattr(os, "PathLike", ())):
        path = os.fspath(path)

    elif hasattr(path, "__fspath__"):
        path = path.__fspath__()

    elif path.__class__.__module__ == "pathlib":
        import pathlib

        if isinstance(path, pathlib.Path):
            path = str(path)

    return path


_windows_drive_letter_ending = re.compile(r".*\b[A-Za-z]$")
_windows_absolute_path_pattern = re.compile(r"^[A-Za-z]:\\")
_windows_absolute_path_pattern_slash = re.compile(r"^/[A-Za-z]:\\")
_might_be_port = re.compile(r"^[0-9].*")


def file_object_path_split(path):
    path = regularize_path(path)

    try:
        index = path.rindex(":")
    except ValueError:
        return path, None
    else:
        file_path, object_path = path[:index], path[index + 1 :]

        if (
            _might_be_port.match(object_path) is not None
            and urlparse(file_path).path == ""
        ):
            return path, None

        file_path = file_path.rstrip()
        object_path = object_path.lstrip()

        if file_path.upper() in ("FILE", "HTTP", "HTTPS", "ROOT"):
            return path, None
        elif (
            os.name == "nt"
            and _windows_drive_letter_ending.match(file_path) is not None
        ):
            return path, None
        else:
            return file_path, object_path


_remote_schemes = ["ROOT", "HTTP", "HTTPS"]
_schemes = ["FILE"] + _remote_schemes


def file_path_to_source_class(file_path, options):
    file_path = regularize_path(file_path)

    windows_absolute_path = None

    if os.name == "nt":
        if _windows_absolute_path_pattern.match(file_path) is not None:
            windows_absolute_path = file_path

    parsed_url = urlparse(file_path)

    if os.name == "nt" and windows_absolute_path is None:
        if _windows_absolute_path_pattern.match(parsed_url.path) is not None:
            windows_absolute_path = parsed_url.path
        elif _windows_absolute_path_pattern_slash.match(parsed_url.path) is not None:
            windows_absolute_path = parsed_url.path[1:]

    if (
        parsed_url.scheme.upper() == "FILE"
        or len(parsed_url.scheme) == 0
        or windows_absolute_path
    ):
        if windows_absolute_path is None:
            if parsed_url.netloc.upper() == "LOCALHOST":
                file_path = parsed_url.path
            else:
                file_path = parsed_url.netloc + parsed_url.path
        else:
            file_path = windows_absolute_path

        return options["file_handler"], os.path.expanduser(file_path)

    elif parsed_url.scheme.upper() == "ROOT":
        return options["xrootd_handler"], file_path

    elif parsed_url.scheme.upper() == "HTTP" or parsed_url.scheme.upper() == "HTTPS":
        return options["http_handler"], file_path

    else:
        raise ValueError("URI scheme not recognized: {0}".format(file_path))


if isinstance(__builtins__, dict):
    if "FileNotFoundError" in __builtins__:
        _FileNotFoundError = __builtins__["FileNotFoundError"]
    else:
        _FileNotFoundError = __builtins__["IOError"]
else:
    if hasattr(__builtins__, "FileNotFoundError"):
        _FileNotFoundError = __builtins__.FileNotFoundError
    else:
        _FileNotFoundError = __builtins__.IOError


def _file_not_found(files, message=None):
    if message is None:
        message = ""
    else:
        message = " (" + message + ")"

    return _FileNotFoundError(
        """file not found{0}

    {1}

Files may be specified as:
   * str/bytes: relative or absolute filesystem path or URL, without any colons
         other than Windows drive letter or URL schema.
         Examples: "rel/file.root", "C:\\abs\\file.root", "http://where/what.root"
   * str/bytes: same with an object-within-ROOT path, separated by a colon.
         Example: "rel/file.root:tdirectory/ttree"
   * pathlib.Path: always interpreted as a filesystem path or URL only (no
         object-within-ROOT path), regardless of whether there are any colons.
         Examples: Path("rel:/file.root"), Path("/abs/path:stuff.root")

Functions that accept many files (uproot4.iterate, etc.) also allow:
   * glob syntax in str/bytes and pathlib.Path.
         Examples: Path("rel/*.root"), "/abs/*.root:tdirectory/ttree"
   * dict: keys are filesystem paths, values are objects-within-ROOT paths.
         Example: {{"/data_v1/*.root": "ttree_v1", "/data_v2/*.root": "ttree_v2"}}
   * already-open TTree objects.
   * iterables of the above.
""".format(
            message, repr(files)
        )
    )


def memory_size(data, error_message=None):
    """
    Regularizes strings like '## kB' and plain integer number of bytes to
    an integer number of bytes.
    """
    if isstr(data):
        m = re.match(
            r"^\s*([+-]?(\d+(\.\d*)?|\.\d+)(e[+-]?\d+)?)\s*([kmgtpezy]?b)\s*$",
            data,
            re.I,
        )
        if m is not None:
            target, unit = float(m.group(1)), m.group(5).upper()
            if unit == "KB":
                target *= 1000
            elif unit == "MB":
                target *= 1000 ** 2
            elif unit == "GB":
                target *= 1000 ** 3
            elif unit == "TB":
                target *= 1000 ** 4
            elif unit == "PB":
                target *= 1000 ** 5
            elif unit == "EB":
                target *= 1000 ** 6
            elif unit == "ZB":
                target *= 1000 ** 7
            elif unit == "YB":
                target *= 1000 ** 8
            elif unit == "KIB":
                target *= 1024
            elif unit == "MIB":
                target *= 1024 ** 2
            elif unit == "GIB":
                target *= 1024 ** 3
            elif unit == "TIB":
                target *= 1024 ** 4
            elif unit == "PIB":
                target *= 1024 ** 5
            elif unit == "EIB":
                target *= 1024 ** 6
            elif unit == "ZIB":
                target *= 1024 ** 7
            elif unit == "YIB":
                target *= 1024 ** 8
            return int(target)

    if isint(data):
        return int(data)

    if error_message is None:
        raise TypeError(
            "number of bytes or memory size string with units "
            "(such as '100 MB') required, not {0}".format(repr(data))
        )
    else:
        raise TypeError(error_message)


def new_class(name, bases, members):
    import uproot4.dynamic

    out = type(ensure_str(name), bases, members)
    out.__module__ = "uproot4.dynamic"
    setattr(uproot4.dynamic, out.__name__, out)
    return out


_primitive_awkward_form = {}


def awkward_form(model, file, index_format="i64", header=False, tobject_header=True):
    import awkward1

    if isinstance(model, numpy.dtype):
        model = model.newbyteorder("=")

        if model not in _primitive_awkward_form:
            if model == numpy.dtype(numpy.bool_) or model == numpy.dtype(numpy.bool):
                _primitive_awkward_form[model] = awkward1.forms.Form.fromjson('"bool"')
            elif model == numpy.dtype(numpy.int8):
                _primitive_awkward_form[model] = awkward1.forms.Form.fromjson('"int8"')
            elif model == numpy.dtype(numpy.uint8):
                _primitive_awkward_form[model] = awkward1.forms.Form.fromjson('"uint8"')
            elif model == numpy.dtype(numpy.int16):
                _primitive_awkward_form[model] = awkward1.forms.Form.fromjson('"int16"')
            elif model == numpy.dtype(numpy.uint16):
                _primitive_awkward_form[model] = awkward1.forms.Form.fromjson(
                    '"uint16"'
                )
            elif model == numpy.dtype(numpy.int32):
                _primitive_awkward_form[model] = awkward1.forms.Form.fromjson('"int32"')
            elif model == numpy.dtype(numpy.uint32):
                _primitive_awkward_form[model] = awkward1.forms.Form.fromjson(
                    '"uint32"'
                )
            elif model == numpy.dtype(numpy.int64):
                _primitive_awkward_form[model] = awkward1.forms.Form.fromjson('"int64"')
            elif model == numpy.dtype(numpy.uint64):
                _primitive_awkward_form[model] = awkward1.forms.Form.fromjson(
                    '"uint64"'
                )
            elif model == numpy.dtype(numpy.float32):
                _primitive_awkward_form[model] = awkward1.forms.Form.fromjson(
                    '"float32"'
                )
            elif model == numpy.dtype(numpy.float64):
                _primitive_awkward_form[model] = awkward1.forms.Form.fromjson(
                    '"float64"'
                )
            else:
                raise AssertionError("{0}: {1}".format(repr(model), type(model)))

        return _primitive_awkward_form[model]

    else:
        return model.awkward_form(file, index_format, header, tobject_header)


def awkward_form_remove_uproot(awkward1, form):
    parameters = dict(form.parameters)
    parameters.pop("uproot", None)
    if isinstance(form, awkward1.forms.BitMaskedForm):
        return awkward1.forms.BitMaskedForm(
            form.mask,
            awkward_form_remove_uproot(awkward1, form.content),
            form.valid_when,
            form.lsb_order,
            form.has_identities,
            parameters,
        )
    elif isinstance(form, awkward1.forms.ByteMaskedForm):
        return awkward1.forms.ByteMaskedForm(
            form.mask,
            awkward_form_remove_uproot(awkward1, form.content),
            form.valid_when,
            form.has_identities,
            parameters,
        )
    elif isinstance(form, awkward1.forms.EmptyForm):
        return awkward1.forms.EmptyForm(form.has_identities, parameters,)
    elif isinstance(form, awkward1.forms.IndexedForm):
        return awkward1.forms.IndexedForm(
            form.index,
            awkward_form_remove_uproot(awkward1, form.content),
            form.has_identities,
            parameters,
        )
    elif isinstance(form, awkward1.forms.IndexedOptionForm):
        return awkward1.forms.IndexedOptionForm(
            form.index,
            awkward_form_remove_uproot(awkward1, form.content),
            form.has_identities,
            parameters,
        )
    elif isinstance(form, awkward1.forms.ListForm):
        return awkward1.forms.ListForm(
            form.starts,
            form.stops,
            awkward_form_remove_uproot(awkward1, form.content),
            form.has_identities,
            parameters,
        )
    elif isinstance(form, awkward1.forms.ListOffsetForm):
        return awkward1.forms.ListOffsetForm(
            form.offsets,
            awkward_form_remove_uproot(awkward1, form.content),
            form.has_identities,
            parameters,
        )
    elif isinstance(form, awkward1.forms.NumpyForm):
        return awkward1.forms.NumpyForm(
            form.inner_shape,
            form.itemsize,
            form.format,
            form.has_identities,
            parameters,
        )
    elif isinstance(form, awkward1.forms.RecordForm):
        return awkward1.forms.RecordForm(
            dict(
                (k, awkward_form_remove_uproot(awkward1, v))
                for k, v in form.contents.items()
            ),
            form.has_identities,
            parameters,
        )
    elif isinstance(form, awkward1.forms.RegularForm):
        return awkward1.forms.RegularForm(
            awkward_form_remove_uproot(awkward1, form.content),
            form.size,
            form.has_identities,
            parameters,
        )
    elif isinstance(form, awkward1.forms.UnionForm):
        return awkward1.forms.UnionForm(
            form.tags,
            form.index,
            [awkward_form_remove_uproot(awkward1, x) for x in form.contents],
            form.has_identities,
            parameters,
        )
    elif isinstance(form, awkward1.forms.UnmaskedForm):
        return awkward1.forms.UnmaskedForm(
            awkward_form_remove_uproot(awkward1, form.content),
            form.has_identities,
            parameters,
        )
    elif isinstance(form, awkward1.forms.VirtualForm):
        return awkward1.forms.VirtualForm(
            awkward_form_remove_uproot(awkward1, form.form),
            form.has_length,
            form.has_identities,
            parameters,
        )
    else:
        raise RuntimeError("unrecognized form: {0}".format(type(form)))


# FIXME: Until we get Awkward reading these bytes directly, rather than
# going through ak.from_iter, the integer dtypes will be int64 and the
# floating dtypes will be float64 because that's what ak.from_iter makes.
def awkward_form_of_iter(awkward1, form):
    if isinstance(form, awkward1.forms.BitMaskedForm):
        return awkward1.forms.BitMaskedForm(
            form.mask,
            awkward_form_of_iter(awkward1, form.content),
            form.valid_when,
            form.lsb_order,
            form.has_identities,
            form.parameters,
        )
    elif isinstance(form, awkward1.forms.ByteMaskedForm):
        return awkward1.forms.ByteMaskedForm(
            form.mask,
            awkward_form_of_iter(awkward1, form.content),
            form.valid_when,
            form.has_identities,
            form.parameters,
        )
    elif isinstance(form, awkward1.forms.EmptyForm):
        return awkward1.forms.EmptyForm(form.has_identities, form.parameters,)
    elif isinstance(form, awkward1.forms.IndexedForm):
        return awkward1.forms.IndexedForm(
            form.index,
            awkward_form_of_iter(awkward1, form.content),
            form.has_identities,
            form.parameters,
        )
    elif isinstance(form, awkward1.forms.IndexedOptionForm):
        return awkward1.forms.IndexedOptionForm(
            form.index,
            awkward_form_of_iter(awkward1, form.content),
            form.has_identities,
            form.parameters,
        )
    elif isinstance(form, awkward1.forms.ListForm):
        return awkward1.forms.ListForm(
            form.starts,
            form.stops,
            awkward_form_of_iter(awkward1, form.content),
            form.has_identities,
            form.parameters,
        )
    elif isinstance(form, awkward1.forms.ListOffsetForm):
        return awkward1.forms.ListOffsetForm(
            form.offsets,
            awkward_form_of_iter(awkward1, form.content),
            form.has_identities,
            form.parameters,
        )
    elif isinstance(form, awkward1.forms.NumpyForm):
        if form.parameter("__array__") in ("char", "byte"):
            f = form
        else:
            d = form.to_numpy()
            if issubclass(d.type, numpy.integer):
                d = numpy.dtype(numpy.int64)
            elif issubclass(d.type, numpy.floating):
                d = numpy.dtype(numpy.float64)
            f = awkward1.forms.Form.from_numpy(d)
        out = awkward1.forms.NumpyForm(
            form.inner_shape,
            f.itemsize,
            f.format,
            form.has_identities,
            form.parameters,
        )
        return out
    elif isinstance(form, awkward1.forms.RecordForm):
        return awkward1.forms.RecordForm(
            dict(
                (k, awkward_form_of_iter(awkward1, v)) for k, v in form.contents.items()
            ),
            form.has_identities,
            form.parameters,
        )
    elif isinstance(form, awkward1.forms.RegularForm):
        return awkward1.forms.RegularForm(
            awkward_form_of_iter(awkward1, form.content),
            form.size,
            form.has_identities,
            form.parameters,
        )
    elif isinstance(form, awkward1.forms.UnionForm):
        return awkward1.forms.UnionForm(
            form.tags,
            form.index,
            [awkward_form_of_iter(awkward1, x) for x in form.contents],
            form.has_identities,
            form.parameters,
        )
    elif isinstance(form, awkward1.forms.UnmaskedForm):
        return awkward1.forms.UnmaskedForm(
            awkward_form_of_iter(awkward1, form.content),
            form.has_identities,
            form.parameters,
        )
    elif isinstance(form, awkward1.forms.VirtualForm):
        return awkward1.forms.VirtualForm(
            awkward_form_of_iter(awkward1, form.form),
            form.has_length,
            form.has_identities,
            form.parameters,
        )
    else:
        raise RuntimeError("unrecognized form: {0}".format(type(form)))
