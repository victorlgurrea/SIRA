"""python -m sira.services.ingesta [--scheduler|--bootstrap]"""
from sira.services.ingesta.runner import main

raise SystemExit(main())
