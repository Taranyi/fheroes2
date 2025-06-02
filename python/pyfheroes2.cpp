#include <Python.h>
#include "settings.h"
#include <SDL_main.h>
#include <vector>
#include <string>

extern "C" int main( int argc, char ** argv );

static PyObject * py_get_version( PyObject *, PyObject * )
{
    const std::string ver = Settings::GetVersion();
    return PyUnicode_FromString( ver.c_str() );
}

static PyObject * py_run_game( PyObject *, PyObject * args )
{
    if ( !PyTuple_Check( args ) ) {
        PyErr_SetString( PyExc_TypeError, "arguments must be a tuple" );
        return nullptr;
    }

    const Py_ssize_t argcPy = PyTuple_Size( args );
    std::vector<char *> argv;
    argv.reserve( static_cast<size_t>( argcPy ) + 1 );
    argv.push_back( const_cast<char *>( "fheroes2" ) );

    for ( Py_ssize_t i = 0; i < argcPy; ++i ) {
        PyObject * item = PyTuple_GetItem( args, i );
        if ( !PyUnicode_Check( item ) ) {
            PyErr_SetString( PyExc_TypeError, "all arguments must be strings" );
            return nullptr;
        }
        argv.push_back( const_cast<char *>( PyUnicode_AsUTF8( item ) ) );
    }
    argv.push_back( nullptr );

    int result = main( static_cast<int>( argv.size() - 1 ), argv.data() );
    return PyLong_FromLong( result );
}

static PyMethodDef fh2Methods[] = {
    { "get_version", py_get_version, METH_NOARGS, "Get fheroes2 version string." },
    { "run_game", py_run_game, METH_VARARGS, "Run fheroes2 with given arguments." },
    { nullptr, nullptr, 0, nullptr }
};

static struct PyModuleDef fh2module = {
    PyModuleDef_HEAD_INIT,
    "fheroes2",   /* name of module */
    "Python bindings for fheroes2.",
    -1,
    fh2Methods
};

PyMODINIT_FUNC PyInit_fheroes2( void )
{
    return PyModule_Create( &fh2module );
}
