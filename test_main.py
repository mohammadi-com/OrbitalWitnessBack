import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
import requests
import json
import re
from main import app, calculate_credits

client = TestClient(app)

class MockResponse:
    """A mock response object to simulate requests responses."""
    def __init__(self, json_data, status_code):
        self.json_data = json_data
        self.status_code = status_code
        self.content = json.dumps(json_data).encode('utf-8')

    def json(self):
        return self.json_data

    def raise_for_status(self):
        if not (200 <= self.status_code < 300):
            raise requests.exceptions.HTTPError(f"{self.status_code} Error")

    @property
    def text(self):
        return json.dumps(self.json_data)

def test_calculate_credits_base_cost():
    text = ""
    credits = calculate_credits(text)
    assert credits == 1  # Base cost only

def test_calculate_credits_character_count():
    text = "abc"
    credits = calculate_credits(text)
    expected_credits = max(1, 1 + 3 * 0.05 + 0.1 -2)  # Base cost + character count + word length - 2 for uniqueness with minumum of 1
    assert credits == expected_credits

def test_calculate_credits_word_lengths():
    text = "I love programming"
    credits = calculate_credits(text)
    expected_credits = max(1, 1 + 18 * 0.05 + 0.1 + 0.2 + 0.3 + 0.3 - 2)  # Base cost + character count + word length + word length + word length + vowel - 2 for uniqueness with minumum of 1
    assert credits == expected_credits

def test_calculate_credits_third_vowels():
    text = "abcdefghi"
    credits = calculate_credits(text)
    expected_credits = max(1, 1 + 9 * 0.05 + 0.3 + 0.3 - 2)  # Base cost + character count + word length + vowel - 2 for uniqueness with minumum of 1

    assert credits == expected_credits

def test_calculate_credits_length_penalty():
    text = "a" * 101
    credits = calculate_credits(text)
    expected_credits = max(1, 1 + 101 * 0.05 + 0.3 + (101//3)*0.3 + 5 - 2)*2  # Base cost + character count + word length + vowel + length penalty - 2 for uniqueness with minumum of 1 then multplied 2 for Palindrome
    assert credits == pytest.approx(expected_credits, 0.0001)

def test_calculate_credits_unique_word_bonus():
    text = "cat dog bird fish"
    credits = calculate_credits(text)
    expected_credits = max(1, 1 + 17 * 0.05 + 2*0.1 + 2*0.2 + 2*0.3 - 2)  # Base cost + character count + word length + vowel - 2 for uniqueness with minumum of 1


    assert credits == pytest.approx(expected_credits, 0.0001)


def test_get_usage_success():
    with patch('requests.get') as mock_get:
        # Mock responses
        messages_response = {
            "messages": [
                {
                    "id": 1,
                    "timestamp": "2023-10-01T00:00:00Z",
                    "text": "Hello world",
                    "report_id": "123"
                },
                {
                    "id": 2,
                    "timestamp": "2023-10-02T00:00:00Z",
                    "text": "Test message"
                }
            ]
        }

        report_response = {
            "id": 123,
            "name": "Test Report",
            "credit_cost": 10
        }

        def mock_get_side_effect(url, *args, **kwargs):
            if "messages/current-period" in url:
                return MockResponse(messages_response, 200)
            elif "reports/123" in url:
                return MockResponse(report_response, 200)
            else:
                return MockResponse({}, 404)

        mock_get.side_effect = mock_get_side_effect

        response = client.get("/usage")
        assert response.status_code == 200
        data = response.json()
        assert "usage" in data
        assert len(data["usage"]) == 2

        # First message
        msg1 = data["usage"][0]
        assert msg1["message_id"] == 1
        assert msg1["report_name"] == "Test Report"
        assert msg1["credits_used"] == 10

        # Second message
        msg2 = data["usage"][1]
        assert msg2["message_id"] == 2
        expected_credits = max(1, 1 + 12 * 0.05 + 2*0.2 -2)  # Base cost + character count + word length - 2 for uniqueness with minumum of 1
        assert msg2["credits_used"] == expected_credits

def test_get_usage_report_404():
    with patch('requests.get') as mock_get:
        messages_response = {
            "messages": [
                {
                    "id": 1,
                    "timestamp": "2023-10-01T00:00:00Z",
                    "text": "Hello world",
                    "report_id": "123"
                }
            ]
        }

        def mock_get_side_effect(url, *args, **kwargs):
            if "messages/current-period" in url:
                return MockResponse(messages_response, 200)
            elif "reports/123" in url:
                return MockResponse({}, 404)
            else:
                return MockResponse({}, 500)

        mock_get.side_effect = mock_get_side_effect

        response = client.get("/usage")
        assert response.status_code == 200
        data = response.json()

        msg = data["usage"][0]
        assert msg["message_id"] == 1
        assert "report_name" not in msg
        expected_credits = calculate_credits("Hello world")
        assert msg["credits_used"] == expected_credits

def test_get_usage_report_error():
    with patch('requests.get') as mock_get:
        messages_response = {
            "messages": [
                {
                    "id": 1,
                    "timestamp": "2023-10-01T00:00:00Z",
                    "text": "Hello world",
                    "report_id": "123"
                }
            ]
        }

        def mock_get_side_effect(url, *args, **kwargs):
            if "messages/current-period" in url:
                return MockResponse(messages_response, 200)
            elif "reports/123" in url:
                return MockResponse({}, 500)
            else:
                return MockResponse({}, 500)

        mock_get.side_effect = mock_get_side_effect

        response = client.get("/usage")
        assert response.status_code == 500
        data = response.json()
        assert data["detail"] == "Failed to fetch report"

def test_get_usage_messages_error():
    with patch('requests.get') as mock_get:
        def mock_get_side_effect(url, *args, **kwargs):
            return MockResponse({}, 500)

        mock_get.side_effect = mock_get_side_effect

        response = client.get("/usage")
        assert response.status_code == 500
        data = response.json()
        assert data["detail"] == "Failed to fetch messages"