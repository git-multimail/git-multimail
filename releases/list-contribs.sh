#!/bin/sh

git shortlog -se "$@" | sort -nr | sed 's/^\s*[0-9][0-9]*\s*/Contributions-by: /'
