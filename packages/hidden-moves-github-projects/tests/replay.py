"""Synthetic transport shared by standalone and consumer-boundary checks."""

import copy
import json
import re
from pathlib import Path

from hidden_moves_github_projects import HTTPResponse

FIXTURE = Path(__file__).parent / "fixtures/projects.json"


class ReplayTransport:
	def __init__(self):
		self.responses = json.loads(FIXTURE.read_text(encoding="utf-8"))
		self.requests = []

	def __call__(self, request, *, timeout, max_bytes):
		payload = json.loads(request.data)
		operation = re.search(r"query (\w+)", payload["query"]).group(1)
		self.requests.append((payload, timeout, max_bytes))
		return HTTPResponse(200, json.dumps(copy.deepcopy(self.responses[operation])).encode())
