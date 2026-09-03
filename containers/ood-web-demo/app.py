#!/usr/bin/env python3

"""
Minimal interactive web application used to validate the Ceres deployment path.

This application intentionally uses only the Python standard library. Its
purpose is not to reproduce drone-pilot-upload functionality. It demonstrates
that:

    Open OnDemand
        -> submits a Slurm job
        -> starts Apptainer on a Ceres compute node
        -> runs an interactive HTTP application inside the container
        -> exposes that application through the Open OnDemand reverse proxy.

The application includes a small HTML form so the demonstration proves
server-side request handling rather than merely serving a static page.
"""

import html
import os
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs


# Open OnDemand chooses an unused TCP port before starting the application.
# template/script.sh.erb passes that value into the container as PORT.
PORT = int(os.environ.get("PORT", "8000"))

# socket.gethostname() executes inside the Apptainer runtime and therefore
# identifies the Ceres compute node on which Slurm started the application.
HOSTNAME = socket.gethostname()

# Slurm exports SLURM_JOB_ID into the application environment. Displaying it
# makes the relationship between the browser application and the scheduled
# Slurm job visible during the demonstration.
SLURM_JOB_ID = os.environ.get("SLURM_JOB_ID", "none")

# Simple process-local state used to demonstrate that requests are being
# handled by a running application process.
request_count = 0


def make_page(message=""):
    """Generate the HTML response returned by the demonstration application."""

    global request_count

    message_html = ""
    if message:
        # Escape user-supplied text before placing it in HTML.
        message_html = f"<p><strong>{html.escape(message)}</strong></p>"

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Drone Pilot Upload Apptainer Demo</title>
</head>
<body>
  <h1>Drone Pilot Upload Apptainer Demo</h1>

  <p>This interactive application is running under Apptainer on Ceres.</p>

  <ul>
    <li>Compute node: {html.escape(HOSTNAME)}</li>
    <li>Slurm job: {html.escape(SLURM_JOB_ID)}</li>
    <li>Requests served: {request_count}</li>
  </ul>

  {message_html}

  <form method="post">
    <label>
      Your name:
      <input name="name" required>
    </label>
    <button type="submit">Submit</button>
  </form>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    """Handle browser requests received through the Open OnDemand proxy."""

    def respond(self, message=""):
        global request_count

        request_count += 1
        body = make_page(message).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        """Render the initial application page."""

        self.respond()

    def do_POST(self):
        """Process the demonstration form and generate a server-side response."""

        length = int(self.headers.get("Content-Length", "0"))
        values = parse_qs(self.rfile.read(length).decode("utf-8"))
        name = values.get("name", [""])[0]

        self.respond(f"Hello, {name}.")


# Bind to all interfaces on the dynamically assigned port so that the Open
# OnDemand reverse proxy can reach the service on the allocated compute node.
server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)

print(
    f"Starting application on {HOSTNAME}:{PORT}; "
    f"Slurm job {SLURM_JOB_ID}",
    flush=True,
)

# Remain in the foreground for the lifetime of the Slurm job. When the user
# cancels the Open OnDemand session, Slurm terminates this process and the
# application becomes unavailable.
server.serve_forever()
