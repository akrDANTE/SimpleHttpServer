import re
import time
import shlex
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from urllib.request import urlopen, Request


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return

        for key, value in attrs:
            if key.lower() == "href":
                self.links.append(value)


class DirectoryDownloader:
    def __init__(
        self,
        remote_shell,
        retries=3,
        retry_delay=5,
    ):
        self.remote_shell = remote_shell
        self.retries = retries
        self.retry_delay = retry_delay

    def get_directory_files(self, directory_url):
        """
        Parse first-level files from directory listing.
        """

        if not directory_url.endswith("/"):
            directory_url += "/"

        html = urlopen(directory_url).read().decode(
            "utf-8",
            errors="ignore",
        )

        parser = LinkParser()
        parser.feed(html)

        files = []

        for href in parser.links:
            if href in ("../", "./", "/"):
                continue

            if href.endswith("/"):
                continue

            files.append(urljoin(directory_url, href))

        return files

    def get_server_file_size(self, url):
        """
        Read Content-Length using HEAD request.
        Returns None if unavailable.
        """

        try:
            req = Request(url, method="HEAD")

            with urlopen(req) as response:
                size = response.headers.get("Content-Length")

                if size is None:
                    return None

                return int(size)

        except Exception:
            return None

    def get_remote_file_size(self, filename):
        """
        Query remote file size.
        """

        cmd = (
            f"stat -c %s {shlex.quote(filename)} "
            f"2>/dev/null || echo FILE_NOT_FOUND"
        )

        output = self.remote_shell.execute(cmd)

        output = output.strip()

        if output == "FILE_NOT_FOUND":
            return None

        try:
            return int(output)
        except Exception:
            return None

    def download_file(self, url):
        """
        Download a single file.
        """

        filename = urlparse(url).path.split("/")[-1]

        expected_size = self.get_server_file_size(url)

        print(f"Downloading {filename}")

        curl_cmd = f"""
curl \
    --fail \
    --location \
    --continue-at - \
    --remote-name \
    {shlex.quote(url)} \
    >/tmp/curl_download.log 2>&1

echo "__RC__$?"
"""

        for attempt in range(1, self.retries + 1):

            output = self.remote_shell.execute(curl_cmd)

            match = re.search(r"__RC__(\d+)", output)

            if not match:
                print(
                    f"{filename}: unable to determine curl exit code"
                )

                time.sleep(self.retry_delay)
                continue

            rc = int(match.group(1))

            if rc != 0:
                print(
                    f"{filename}: curl failed "
                    f"(attempt {attempt}/{self.retries}) "
                    f"rc={rc}"
                )

                time.sleep(self.retry_delay)
                continue

            if expected_size is not None:

                actual_size = self.get_remote_file_size(
                    filename
                )

                if actual_size != expected_size:

                    print(
                        f"{filename}: size mismatch "
                        f"(attempt {attempt}/{self.retries}) "
                        f"expected={expected_size} "
                        f"actual={actual_size}"
                    )

                    time.sleep(self.retry_delay)
                    continue

            print(f"{filename}: success")
            return True

        print(f"{filename}: FAILED")
        return False

    def download_directory(self, directory_url):
        files = self.get_directory_files(directory_url)

        print(f"Found {len(files)} files")

        failed = []

        for file_url in files:

            success = self.download_file(file_url)

            if not success:
                failed.append(file_url)

        return failed
