"""Restrict the workload before executing an untrusted compiler input or service."""

import ctypes as c
import errno
import os
import resource
import socket
import sys


class Comparison(c.Structure):
    _fields_ = [("arg", c.c_uint), ("op", c.c_int), ("a", c.c_uint64), ("b", c.c_uint64)]


def restrict_syscalls():
    lib = c.CDLL("libseccomp.so.2")
    lib.seccomp_init.argtypes = [c.c_uint32]
    lib.seccomp_init.restype = c.c_void_p
    lib.seccomp_syscall_resolve_name.argtypes = [c.c_char_p]
    lib.seccomp_rule_add_array.argtypes = [c.c_void_p, c.c_uint32, c.c_int, c.c_uint, c.POINTER(Comparison)]
    lib.seccomp_load.argtypes = [c.c_void_p]
    lib.seccomp_release.argtypes = [c.c_void_p]
    context = lib.seccomp_init(0x7FFF0000)  # SCMP_ACT_ALLOW
    if not context:
        raise RuntimeError("cannot create syscall filter")

    def deny(name, *arguments):
        syscall = lib.seccomp_syscall_resolve_name(name.encode())
        comparisons = (Comparison * len(arguments))(*arguments)
        result = lib.seccomp_rule_add_array(context, 0x00050000 | errno.EPERM, syscall, len(arguments), comparisons)
        if result < 0:
            raise OSError(-result, f"cannot restrict {name}")

    try:
        # Accept TCP requests but do not initiate connections or send datagrams.
        # SCMP_CMP_NE and SCMP_CMP_MASKED_EQ are 1 and 7, respectively.
        deny("socket", (0, 1, socket.AF_INET, 0))
        for kind in (socket.SOCK_DGRAM, socket.SOCK_RAW, socket.SOCK_SEQPACKET, socket.SOCK_RDM):
            deny("socket", (1, 7, 0xF, kind))
        deny("sendto", (4, 1, 0, 0))  # send() supplies a null destination
        for name in (
            "connect", "sendmsg", "sendmmsg", "io_uring_setup", "ptrace", "process_vm_readv",
            "process_vm_writev", "kill", "tkill", "tgkill", "pidfd_send_signal", "setsid", "setpgid",
        ):
            deny(name)
        result = lib.seccomp_load(context)
        if result < 0:
            raise OSError(-result, "cannot load syscall filter")
    finally:
        lib.seccomp_release(context)


if __name__ == "__main__":
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
    resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024**2, 16 * 1024**2))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
    resource.setrlimit(resource.RLIMIT_NPROC, (32, 32))
    restrict_syscalls()
    os.execv(sys.argv[1], sys.argv[1:])
