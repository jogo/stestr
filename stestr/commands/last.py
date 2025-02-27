# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

"""Show the last run loaded into a repository."""

import sys

from cliff import command

from stestr import output
from stestr.repository import abstract
from stestr.repository import util
from stestr import results
from stestr import subunit_trace
from stestr import user_config


class Last(command.Command):
    """Show the last run loaded into a repository.

    Failing tests are shown on the console and a summary of the run is
    printed at the end.

    Without --subunit, the process exit code will be non-zero if the test
    run was not successful. With --subunit, the process exit code is
    non-zero only if the subunit stream could not be generated
    successfully. The test results and run status are included in the
    subunit stream, so the stream should be used to determining the result
    of the run instead of the exit code when using the --subunit flag.
    """

    def get_parser(self, prog_name):
        parser = super().get_parser(prog_name)
        parser.add_argument(
            "--subunit", action="store_true",
            default=False, help="Show output as a subunit stream.")
        parser.add_argument("--no-subunit-trace", action='store_true',
                            default=False,
                            help="Disable output with the subunit-trace "
                            "output filter")
        parser.add_argument('--force-subunit-trace', action='store_true',
                            default=False,
                            help='Force subunit-trace output regardless of any'
                                 'other options or config settings')
        parser.add_argument('--color', action='store_true', default=False,
                            help='Enable color output in the subunit-trace '
                            'output, if subunit-trace output is enabled. '
                            '(this is the default). If subunit-trace is '
                            'disable this does nothing.')
        parser.add_argument('--suppress-attachments', action='store_true',
                            dest='suppress_attachments',
                            help='If set do not print stdout or stderr '
                            'attachment contents on a successful test '
                            'execution')
        parser.add_argument('--all-attachments', action='store_true',
                            dest='all_attachments',
                            help='If set print all text attachment contents on'
                            ' a successful test execution')
        parser.add_argument('--show-binary-attachments', action='store_true',
                            dest='show_binary_attachments',
                            help='If set, show non-text attachments. This is '
                            'generally only useful for debug purposes.')
        return parser

    def take_action(self, parsed_args):
        user_conf = user_config.get_user_config(self.app_args.user_config)
        args = parsed_args
        if args.suppress_attachments and args.all_attachments:
            msg = ("The --suppress-attachments and --all-attachments "
                   "options are mutually exclusive, you can not use both "
                   "at the same time")
            print(msg)
            sys.exit(1)
        if getattr(user_conf, 'last', False):
            if not user_conf.last.get('no-subunit-trace'):
                if not args.no_subunit_trace:
                    pretty_out = True
                else:
                    pretty_out = False
            else:
                pretty_out = False
            pretty_out = args.force_subunit_trace or pretty_out
            color = args.color or user_conf.last.get('color', False)
            suppress_attachments_conf = user_conf.run.get(
                'suppress-attachments', False)
            all_attachments_conf = user_conf.run.get(
                'all-attachments', False)
            if not args.suppress_attachments and not args.all_attachments:
                suppress_attachments = suppress_attachments_conf
                all_attachments = all_attachments_conf
            elif args.suppress_attachments:
                all_attachments = False
                suppress_attachments = args.suppress_attachments
            elif args.all_attachments:
                suppress_attachments = False
                all_attachments = args.all_attachments
        else:
            pretty_out = args.force_subunit_trace or not args.no_subunit_trace
            color = args.color
            suppress_attachments = args.suppress_attachments
            all_attachments = args.all_attachments
        return last(repo_url=self.app_args.repo_url,
                    subunit_out=args.subunit, pretty_out=pretty_out,
                    color=color, suppress_attachments=suppress_attachments,
                    all_attachments=all_attachments,
                    show_binary_attachments=args.show_binary_attachments)


def last(repo_url=None, subunit_out=False, pretty_out=True,
         color=False, stdout=sys.stdout, suppress_attachments=False,
         all_attachments=False, show_binary_attachments=False):
    """Show the last run loaded into a a repository

    This function will print the results from the last run in the repository
    to STDOUT. It can optionally print the subunit stream for the last run
    to STDOUT if the ``subunit`` option is set to true.

    Note this function depends on the cwd for the repository if `repo_url` is
    not specified it will use the repository located at CWD/.stestr

    :param str repo_url: The url of the repository to use.
    :param bool subunit_out: Show output as a subunit stream.
    :param pretty_out: Use the subunit-trace output filter.
    :param color: Enable colorized output with the subunit-trace output filter.
    :param bool subunit: Show output as a subunit stream.
    :param file stdout: The output file to write all output to. By default
         this is sys.stdout
    :param bool suppress_attachments: When set true attachments subunit_trace
        will not print attachments on successful test execution.
    :param bool all_attachments: When set true subunit_trace will print all
        text attachments on successful test execution.
    :param bool show_binary_attachments: When set to true, subunit_trace will
        print binary attachments in addition to text attachments.

    :return return_code: The exit code for the command. 0 for success and > 0
        for failures.
    :rtype: int
    """
    try:
        repo = util.get_repo_open(repo_url=repo_url)
    except abstract.RepositoryNotFound as e:
        stdout.write(str(e) + '\n')
        return 1

    try:
        latest_run = repo.get_latest_run()
    except KeyError as e:
        stdout.write(str(e) + '\n')
        return 1

    if subunit_out:
        stream = latest_run.get_subunit_stream()
        output.output_stream(stream, output=stdout)
        # Exits 0 if we successfully wrote the stream.
        return 0
    case = latest_run.get_test()
    try:
        previous_run = repo.get_test_run(repo.latest_id() - 1)
    except KeyError:
        previous_run = None
    failed = False
    if not pretty_out:
        output_result = results.CLITestResult(latest_run.get_id, stdout,
                                              previous_run)
        summary = output_result.get_summary()
        output_result.startTestRun()
        try:
            case.run(output_result)
        finally:
            output_result.stopTestRun()
        failed = not results.wasSuccessful(summary)
    else:
        stream = latest_run.get_subunit_stream()
        failed = subunit_trace.trace(
            stream, stdout, post_fails=True, color=color,
            suppress_attachments=suppress_attachments,
            all_attachments=all_attachments,
            show_binary_attachments=show_binary_attachments)
    if failed:
        return 1
    else:
        return 0
