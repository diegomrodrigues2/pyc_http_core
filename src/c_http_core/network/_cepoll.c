#include <Python.h>
#include <sys/epoll.h>
#include <unistd.h>

static PyObject *cepoll_create(PyObject *self, PyObject *args) {
    int size;
    if (!PyArg_ParseTuple(args, "i", &size)) {
        return NULL;
    }
    int fd = epoll_create(size);
    if (fd == -1) {
        return PyErr_SetFromErrno(PyExc_OSError);
    }
    return PyLong_FromLong(fd);
}

static PyObject *cepoll_ctl(PyObject *self, PyObject *args) {
    int epfd, op, fd;
    unsigned int events;
    if (!PyArg_ParseTuple(args, "iiiI", &epfd, &op, &fd, &events)) {
        return NULL;
    }
    struct epoll_event ev;
    ev.events = events;
    ev.data.fd = fd;
    if (epoll_ctl(epfd, op, fd, &ev) == -1) {
        return PyErr_SetFromErrno(PyExc_OSError);
    }
    Py_RETURN_NONE;
}

static PyObject *cepoll_wait(PyObject *self, PyObject *args) {
    int epfd, maxevents, timeout;
    if (!PyArg_ParseTuple(args, "iii", &epfd, &maxevents, &timeout)) {
        return NULL;
    }
    struct epoll_event *events = PyMem_Malloc(sizeof(struct epoll_event) * maxevents);
    if (!events) {
        return PyErr_NoMemory();
    }
    int n = epoll_wait(epfd, events, maxevents, timeout);
    if (n == -1) {
        PyMem_Free(events);
        return PyErr_SetFromErrno(PyExc_OSError);
    }
    PyObject *list = PyList_New(n);
    for (int i = 0; i < n; i++) {
        PyObject *t = Py_BuildValue("(ii)", events[i].data.fd, events[i].events);
        PyList_SET_ITEM(list, i, t);  // steals reference
    }
    PyMem_Free(events);
    return list;
}

static PyMethodDef CepollMethods[] = {
    {"create", cepoll_create, METH_VARARGS, "create epoll instance"},
    {"ctl", cepoll_ctl, METH_VARARGS, "control epoll"},
    {"wait", cepoll_wait, METH_VARARGS, "wait for events"},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef cepollmodule = {
    PyModuleDef_HEAD_INIT,
    "_cepoll",
    "Low level epoll wrapper",
    -1,
    CepollMethods
};

PyMODINIT_FUNC PyInit__cepoll(void) {
    PyObject *m = PyModule_Create(&cepollmodule);
    if (!m) return NULL;
    PyModule_AddIntConstant(m, "EPOLLIN", EPOLLIN);
    PyModule_AddIntConstant(m, "EPOLLOUT", EPOLLOUT);
    PyModule_AddIntConstant(m, "EPOLLERR", EPOLLERR);
    PyModule_AddIntConstant(m, "EPOLLHUP", EPOLLHUP);
    PyModule_AddIntConstant(m, "EPOLLET", EPOLLET);
#ifdef EPOLLONESHOT
    PyModule_AddIntConstant(m, "EPOLLONESHOT", EPOLLONESHOT);
#endif
    PyModule_AddIntConstant(m, "EPOLL_CTL_ADD", EPOLL_CTL_ADD);
    PyModule_AddIntConstant(m, "EPOLL_CTL_MOD", EPOLL_CTL_MOD);
    PyModule_AddIntConstant(m, "EPOLL_CTL_DEL", EPOLL_CTL_DEL);
    return m;
}
