#!/bin/sh

test_description="Quick sanity checks"
. ./sharness.sh || exit 1
. "$SHARNESS_TEST_DIRECTORY"/helper-functions.sh || exit 1
D=$SHARNESS_TEST_DIRECTORY

for c in \
    python \
    pep8 \
    git \
    rstcheck \
    pyflakes pyflakes3 \
    ;
do
    unset "${c}"_installed
    ver=unavailable
    case $c in
	python)
	    cmd=$PYTHON
	    ;;
	*)
	    cmd=$c
	    ;;
    esac
    if command -v "${cmd}" >/dev/null 2>&1
    then
	ver=$("${cmd}" --version 2>&1)
	ver=${ver##* }
	test_set_prereq "$c"
    fi
    log "# $c version: $ver"
    if test "$ver" = unavailable
    then
	case "$c" in
	    pep8|rstcheck)
		log "#   (please install it with e.g. 'pip install ${c}' to allow sanity checks)"
		;;
	    *)
		log "#   (please install it to run the complete testsuite)"
		;;
	esac
    fi
done

log "#"

test_expect_success pyflakes 'pyflakes' '
	pyflakes $D/..
'

test_expect_success pyflakes3 'pyflakes3' '
	pyflakes3 $D/..
'

test_expect_success 'Simple but verbose git-multimail run' '
	if "$MULTIMAIL" --stdout \
		HEAD HEAD^ HEAD \
		 --recipient=recipient@example.com >out 2>err
	then
		echo "Command ran OK, now checking stderr"
	else
		echo "Error running $MULTIMAIL, output below:" &&
		cat out && cat err && false
	fi &&
	cat <<-\EOF >expect-err &&
	*** Push-update of strange reference '\''HEAD'\''
	***  - incomplete email generated.
	Sending notification emails to: recipient@example.com
	EOF
	test_cmp err expect-err &&
	echo "stderr OK, now checking stdout" &&
	grep "^To: recipient@example.com" out &&
	echo "Everything all right."
'

# E402: module level import not at top of file => we need this in the
# tests.
#
# E123: closing bracket does not match indentation of opening bracket's line
# => not raised on all pep8 version, and really constraining. We can
# probably keep ignoring it forever.
pep8_file () {
    f=$1
    test_expect_success pep8 "pep8 $f" '
	pep8 "$D"/../"$f" --ignore=E402,E123 --max-line-length=99
    '
}
pep8_file git-multimail/git_multimail.py
pep8_file t/test-env
pep8_file setup.py

rstcheck_file () {
    f=$1
    test_expect_success rstcheck "rstcheck $f" '
	status=0 &&
	rstcheck "$D"/../"$f" >rstcheck.out 2>&1 || status=$? &&
	cat rstcheck.out &&
	! test -s rstcheck.out &&
	return $status
    '
}
rstcheck_file README.rst
rstcheck_file CONTRIBUTING.rst
rstcheck_file doc/gitolite.rst
rstcheck_file doc/gerrit.rst
rstcheck_file t/README.rst

test_expect_success git "sign-off" '
    "$D"/check-sign-off
'

# Test that each documented variable appears at least once outside
# comments in the testsuite. It does not give real coverage garantee,
# and we have known untested variables in untested-variables.txt, but
# this should ensure that new variables get a test.
test_expect_success 'Tests for each configuration variable' '
	variables=$(grep "^multimailhook." $D/../git-multimail/README |
		sed "s/, /\n/g" |
		sed "s/multimailhook\.//") &&
	(
	cd "$D" &&
	status=0 &&
	for v in $variables; do
		if ! git grep -i "^[^#]*$v" >/dev/null
		then
			echo "No occurence of documented variable $v in testsuite" &&
			status=1
		fi
	done
	return $status
	)
'

test_expect_success 'list of untested variables is accurate' '
	cd "$D" &&
	status=0 &&
	for v in $(cat untested-variables.txt); do
		if git grep -i "^[^#]*$v" $(git ls-files | grep -v untested-variables)>/dev/null
		then
			echo "$v appears in untested-variables.txt but also in the testsuite" &&
			status=1
		fi
	done &&
	return $status
'

test_done
