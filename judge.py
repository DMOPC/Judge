#!/usr/bin/python
import os
import Queue
import traceback
import sys
import thread
import threading

import execute

import packet


class Result(object):
    AC = 0x0
    WA = 0x1
    RTE = 0x2
    TLE = 0x4

    def __init__(self):
        self.result_flag = 0
        self.execution_time = 0
        self.max_memory = 0
        self.partial_output = None


class Judge(object):
    def __init__(self, host, port):
        self.packet_manager = packet.PacketManager(host, port, self)
        self.current_submission = None

    def run(self, arguments, iofiles):
        self.packet_manager.begin_grading_packet()
        with ProgramJudge(arguments) as judge:
            for input_file, output_file in iofiles.iteritems():
                result = Result()
                judge.run(result, input_file, output_file)
                self.packet_manager.test_case_status_packet(result.result_flag, result.execution_time,
                                                            result.max_memory,
                                                            result.partial_output)
                yield result
        self.packet_manager.grading_end_packet()

    def begin_grading(self, problem_id, language, source_code):
        pass

    # TODO: cleanup packet manager
    def __del__(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        pass


class ProgramJudge(object):
    EOF = ""

    def __init__(self, processname, redirect=False, transfer=False, interact=False):
        self.result = None
        self.process = execute.execute(processname)
        self.write_lock = threading.Lock()
        self.write_queue = Queue.Queue()
        self.stopped = False
        self.exitcode = None
        self.processname = processname
        self.redirect = redirect
        self.transfer = transfer
        self.interact = interact

        self.old_stdin = sys.stdin
        self.old_stdout = sys.stdout
        self.current_submission = None
        if self.redirect:
            sys.stdin = self
            sys.stdout = self

    def __del__(self):
        self.close(True)

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        self.close()

    def alive(self, result_flag=None):
        if not self.stopped:
            self.exitcode = self.process.poll()
            if self.exitcode is not None:
                sys.stdin = self.old_stdin
                sys.stdout = self.old_stdout
                self.stopped = True
                self.result.result_flag = result_flag
                self.write_lock.acquire()
        return not self.stopped

    def close(self, force_terminate=False, result_flag=None):
        if self.result and self.alive(result_flag):
            self.result.result_flag = result_flag
            self.write_lock.acquire()
            sys.stdin = self.old_stdin
            sys.stdout = self.old_stdout
            if force_terminate or self.interact:
                self.process.terminate()
            else:
                self.exitcode = self.process.wait()
            self.stopped = True

    def read(self, *args):
        return self.process.stdout.read(*args) if self.alive() else ""

    def readline(self):
        if not self.alive():
            return ""
        line = self.process.stdout.readline().rstrip()
        while not line and self.alive():
            line = self.process.stdout.readline().rstrip()
        return line.rstrip() if line else ""

    def run(self, result, input_file, output_file):
        self.result = result
        if self.transfer:
            self.write(sys.stdin.read())
        thread.start_new_thread(self.write_async, (self.write_lock,))
        result_flag = 0
        with open(input_file, "r") as fi, open(output_file, "r") as fo:
            self.write(fi.read().strip())
            self.write(ProgramJudge.EOF)
            process_output = self.read().strip().replace('\r\n', '\n')
            self.result.partial_output = process_output[:10]
            self.result.max_memory = self.process.get_max_memory()
            self.result.execution_time = self.process.get_execution_time()
            judge_output = fo.read().strip().replace('\r\n', '\n')
            if process_output != judge_output:
                result_flag |= Result.WA
        self.close(result_flag=result_flag)

    def write(self, data):
        self.write_queue.put_nowait(data)

    def write_async(self, write_lock):
        try:
            while True:
                while write_lock.acquire(False) and self.alive():
                    write_lock.release()
                    try:
                        data = self.write_queue.get(False, 1)
                        break
                    except:
                        pass
                else:
                    break
                if data == ProgramJudge.EOF:
                    self.process.stdin.close()
                    break
                else:
                    data = data.replace('\r\n', '\n').replace('\r', '\n')
                    self.process.stdin.write(data)
                    if data == '\n':
                        self.process.stdin.flush()
                        os.fsync(self.process.stdin.fileno())
        except Exception:
            traceback.print_exc()


def main():
    # TODO: argparse
    with Judge("127.0.0.1", 8080) as judge:
        try:
            case = 1
            for res in judge.run([sys.executable, "aplusb.py"], {"aplusb.in": "aplusb.out"}):
                print "Test case %s" % case
                print "\t%f seconds" % res.execution_time
                print "\t%.2f mb (%s kb)" % (res.max_memory / 1024.0, res.max_memory)
                if res.result_flag & Result.WA:
                    print "\tWrong Answer"
                else:
                    print "\tAccepted"
                case += 1
        except Exception:
            traceback.print_exc()

    print "Done"


if __name__ == "__main__":
    main()
