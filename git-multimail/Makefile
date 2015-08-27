git_multimail3.py: git_multimail.py
	cp git_multimail.py git_multimail3.py
	2to3 -w -f except git_multimail3.py
	perl -pi -e 's/python2/python3/' git_multimail3.py
	chmod +x git_multimail3.py
