
import asyncio
import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

# Ensure we can import worker_app
sys.path.insert(0, os.getcwd())

from worker_app.main import app, MediaError, ProcessingError, _validate_media_file, GenerateRequest

class TestWorkerErrorReporting(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        
    def test_hc(self):
        """Test health check still works"""
        response = self.client.get("/hc")
        self.assertEqual(response.status_code, 200)
        # Check simply for status ok, ignoring extra fields for now to avoid fragility
        self.assertEqual(response.json().get("status"), "ok")

    @patch("worker_app.main._download_to_temp")
    def test_media_error_download(self, mock_download):
        """Test that download failure results in 422 MediaError"""
        # Mock download to raise MediaError (mimicking DownloadError which inherits MediaError)
        mock_download.side_effect = MediaError(
            stage="download",
            message="Download failed: 404 Not Found",
            details={"url": "http://bad.url", "status_code": 404}
        )
        
        payload = {
            "musetalk_job_id": "test-job-1",
            "video_url": "http://bad.url",
            "audio_url": "http://valid.url",
            "aspect_ratio": "16:9",
            "resolution": "720p"
        }
        
        response = self.client.post("/generate", json=payload)
        
        self.assertEqual(response.status_code, 422)
        data = response.json()
        self.assertEqual(data["status"], "failed")
        self.assertEqual(data["error_type"], "media_error")
        self.assertEqual(data["stage"], "download")
        self.assertEqual(data["retryable"], False)
        print(f"\n✅ MediaError Test Passed: {data}")

    @patch("worker_app.main._download_to_temp")
    @patch("worker_app.main._validate_media_file")
    def test_media_error_validation(self, mock_validate, mock_download):
        """Test that validation failure results in 422 MediaError"""
        # Mock successful download
        mock_download.return_value = "/tmp/fake.mp4"
        
        # Mock validation to raise MediaError
        mock_validate.side_effect = MediaError(
            stage="validation",
            message="Invalid video file",
            details={"path": "/tmp/fake.mp4"}
        )
        
        payload = {
            "musetalk_job_id": "test-job-2",
            "video_url": "http://valid.url/badvid.mp4",
            "audio_url": "http://valid.url/audio.wav",
            "aspect_ratio": "16:9",
            "resolution": "720p"
        }
        
        response = self.client.post("/generate", json=payload)
        
        self.assertEqual(response.status_code, 422)
        data = response.json()
        self.assertEqual(data["status"], "failed")
        self.assertEqual(data["error_type"], "media_error")
        self.assertEqual(data["stage"], "validation")
        print(f"\n✅ Validation Error Test Passed: {data}")

    @patch("worker_app.main._download_to_temp")
    @patch("worker_app.main._validate_media_file")
    @patch("worker_app.main._run_musetalk_inference")
    def test_processing_error_inference(self, mock_inference, mock_validate, mock_download):
        """Test that inference failure results in 500 ProcessingError"""
        mock_download.return_value = "/tmp/fake.mp4"
        mock_validate.return_value = None
        
        # Mock inference to raise ProcessingError
        mock_inference.side_effect = ProcessingError(
            stage="inference",
            message="CUDA out of memory",
            details={"memory": "0MB"},
            retryable=True
        )
        
        payload = {
            "musetalk_job_id": "test-job-3",
            "video_url": "http://valid.url",
            "audio_url": "http://valid.url",
            "aspect_ratio": "16:9",
            "resolution": "720p"
        }
        
        response = self.client.post("/generate", json=payload)
        
        self.assertEqual(response.status_code, 500)
        data = response.json()
        self.assertEqual(data["status"], "failed")
        self.assertEqual(data["error_type"], "processing_error")
        self.assertEqual(data["stage"], "inference")
        self.assertEqual(data["retryable"], True)
        self.assertIn("stack_trace", data)
        print(f"\n✅ Processing Error Test Passed: {data}")

    def test_validate_media_file_real(self):
        """Test _validate_media_file with actual file check logic"""
        # Test non-existent file
        try:
            _validate_media_file("/non/existent/path.mp4", "video")
            self.fail("Should have raised MediaError")
        except MediaError as e:
            self.assertEqual(e.stage, "validation")
            self.assertIn("not found", e.message)
            print(f"\n✅ Validation Logic (Not Found) Test Passed: {e}")

if __name__ == '__main__':
    unittest.main()
