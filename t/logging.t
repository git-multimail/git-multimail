#!/bin/sh

test_description="Python unit-tests"
. ./sharness.sh || exit 1
. "$SHARNESS_TEST_DIRECTORY"/helper-functions.sh || exit 1

test_expect_success 'setup' '
	git init . &&
	git config user.name "John Smith" &&
	git config user.email "John@example.com" &&
	git config multimailhook.mailingList foo@example.com &&
	echo one >file && git add . && git commit -m one &&
	echo two >file && git add . && git commit -m two
'

test_expect_success 'log to file' '
	"$PYTHON" "$MULTIMAIL" --stdout \
		-c multimailhook.logFile=logFile.txt \
		refs/heads/master HEAD^ HEAD >stdout 2>stderr &&
	test -s stdout &&
	! grep -F "[" stderr &&
	grep "^Sending" stderr &&
	! grep -F "[DEBUG]" logFile.txt &&
	grep -F "[INFO ]  Sending notification emails to: foo@example.com" logFile.txt
'

test_expect_success 'log errors to file' '
	rm -f logFile.txt errorLogFile.txt &&
	test_must_fail "$PYTHON" "$MULTIMAIL" \
		-c multimailhook.mailer=nosuchmailer \
		-c multimailhook.errorLogFile=errorLogFile.txt \
		refs/heads/master HEAD^ HEAD &&
	! grep -F "[DEBUG]" errorLogFile.txt &&
	! grep -F "[INFO]" errorLogFile.txt &&
	grep -F "[ERROR]  fatal: multimailhook.mailer is set to an incorrect value: \"nosuchmailer\"" errorLogFile.txt
'

test_expect_success 'log errors to both file' '
	rm -f logFile.txt errorLogFile.txt &&
	test_must_fail "$PYTHON" "$MULTIMAIL" \
		-c multimailhook.mailer=nosuchmailer \
		-c multimailhook.errorLogFile=errorLogFile.txt \
		-c multimailhook.logFile=logFile.txt \
		refs/heads/master HEAD^ HEAD >stdout 2>stderr &&
	test -e stdout && ! test -s stdout &&
	! grep -F "[" stderr &&
	grep "^fatal: " stderr &&
	! grep -F "[DEBUG]" errorLogFile.txt &&
	grep -F "[ERROR]  fatal: multimailhook.mailer is set to an incorrect value: \"nosuchmailer\"" errorLogFile.txt &&
	grep -F "[ERROR]  fatal: multimailhook.mailer is set to an incorrect value: \"nosuchmailer\"" logFile.txt
'

test_expect_success 'log debug to both file' '
	rm -f logFile.txt errorLogFile.txt debugLogFile.txt &&
	test_must_fail "$PYTHON" "$MULTIMAIL" \
		-c multimailhook.mailer=nosuchmailer \
		-c multimailhook.debugLogFile=debugLogFile.txt \
		-c multimailhook.logFile=logFile.txt \
		refs/heads/master HEAD^ HEAD &&
	! grep -F "[DEBUG]" logFile.txt &&
	grep -F "[ERROR]  fatal: multimailhook.mailer is set to an incorrect value: \"nosuchmailer\"" debugLogFile.txt &&
	grep -F "[ERROR]  fatal: multimailhook.mailer is set to an incorrect value: \"nosuchmailer\"" logFile.txt
'

test_expect_success 'verbose output' '
	"$PYTHON" "$MULTIMAIL" --stdout \
		-c multimailhook.verbose=1 \
		refs/heads/master HEAD^ HEAD 2>stderr
	grep "^run_as_update_hook: " stderr
'

test_done
