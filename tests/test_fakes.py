"""Unit tests for testing fakes (LLMClient, MessagingProvider, Storage)."""

from pathlib import Path

from app.llm.client import FakeLLMClient
from app.llm.schemas import Plan, RevisionRequest
from app.messaging.base import FakeMessagingProvider
from app.storage.local import LocalStorage


def test_fake_llm_client_with_canned_dict() -> None:
    """Test that FakeLLMClient parses and returns canned dictionary for requested schema."""
    fake_plan = {
        "template": "offer",
        "target_duration_s": 15.0,
        "segments": [{"clip_id": 1, "start": 0.0, "end": 2.0}],
        "hook_text": "₹99 combo alert!",
        "on_screen_lines": ["Special momo combo", "Only till 8 PM"],
        "offer_text": "Combo 99",
        "price_inr": 99,
        "call_to_action": "Aaj hi aao campus ke paas",
        "caption": "Best combo for students! #momo",
        "hashtags": ["#foodie", "#momo", "#delhi", "#combo", "#offer"],
        "language": "hinglish",
    }
    client = FakeLLMClient(canned_responses={Plan: fake_plan})
    result = client.generate_json(prompt="Plan reel", schema=Plan)

    assert isinstance(result, Plan)
    assert result.template == "offer"
    assert result.price_inr == 99
    assert len(client.call_history) == 1


def test_fake_llm_client_with_sequential_queue() -> None:
    """Test that FakeLLMClient works with sequential response queue."""
    client = FakeLLMClient(
        canned_responses=[
            {"approve": True},
            {"shorter": True},
        ]
    )
    res1 = client.generate_json("Msg 1", schema=RevisionRequest)
    assert res1.approve is True
    res2 = client.generate_json("Msg 2", schema=RevisionRequest)
    assert res2.shorter is True


def test_fake_messaging_provider_records_messages() -> None:
    """Test that FakeMessagingProvider records sent texts and videos."""
    provider = FakeMessagingProvider()
    txt_id = provider.send_text("+919876543210", "Namaste!")
    assert txt_id.startswith("mock_text_")
    assert len(provider.sent_messages) == 1
    assert provider.sent_messages[0]["body"] == "Namaste!"

    vid_id = provider.send_video("+919876543210", "https://example.com/reel.mp4", "Reel preview")
    assert vid_id.startswith("mock_video_")
    assert len(provider.sent_messages) == 2
    assert provider.sent_messages[1]["type"] == "video"
    assert provider.sent_messages[1]["caption"] == "Reel preview"

    tmp_dest = "out/fake_media.mp4"
    saved = provider.download_media("https://example.com/media/1", tmp_dest)
    assert Path(saved).exists()



def test_local_storage_save_and_read(tmp_path: Path) -> None:
    """Test saving and retrieving files using LocalStorage."""
    storage = LocalStorage(base_dir=str(tmp_path))
    content = b"sample video bytes"
    rel_path = "campaigns/1/clip.mp4"

    saved_path = storage.save(content, rel_path)
    assert Path(saved_path).exists()

    read_bytes = storage.get(rel_path)
    assert read_bytes == content

    local_path = storage.get_local_path(rel_path)
    assert local_path.is_file()
    assert local_path.read_bytes() == content
