import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from narration_queue import NarrationQueue, split_for_duration


def test_split_keeps_words_and_sentence_boundaries():
    text = ("Esta é a primeira frase. " * 8) + ("Esta é a segunda frase! " * 8)
    chunks = split_for_duration(text, target_seconds=15, chars_per_minute=300)
    assert len(chunks) > 1
    assert all(chunk.strip() for chunk in chunks)
    assert "  " not in " ".join(chunks)
    assert "primeira" in " ".join(chunks)
    assert "segunda" in " ".join(chunks)


def test_split_empty_and_long_sentence():
    assert split_for_duration("   ") == []
    chunks = split_for_duration("palavra " * 100, target_seconds=15, chars_per_minute=300)
    assert len(chunks) > 1
    assert all(not chunk.startswith(" ") and not chunk.endswith(" ") for chunk in chunks)


def test_queue_persists_and_runs_sequentially(tmp_path):
    path = tmp_path / "queue.sqlite3"
    queue = NarrationQueue(path)
    first = queue.enqueue("Texto A", "voz-a", "voxcpm2", ["Parte A"])
    second = queue.enqueue("Texto B", "voz-b", "f5-tts", ["Parte B"])
    assert queue.claim_next()["id"] == first["id"]
    assert queue.claim_next() is None
    queue.finish(first["id"])
    assert queue.claim_next()["id"] == second["id"]
    reopened = NarrationQueue(path)
    assert reopened.get(second["id"])["status"] == "processing"
    assert reopened.recover_interrupted() == 1
    assert reopened.get(second["id"])["status"] == "interrupted"
    assert reopened.requeue(second["id"])["status"] == "queued"


def test_regeneration_waits_for_approval(tmp_path):
    queue = NarrationQueue(tmp_path / "queue.sqlite3")
    job = queue.enqueue("Texto", "voz", "voxcpm2", ["Parte 1", "Parte 2"])
    candidate = queue.stage_candidate(job["id"], 1, "candidate-part-2.wav")
    assert queue.get(job["id"])["parts"][1]["audio_path"] is None
    approved = queue.approve_candidate(candidate)
    assert approved["parts"][1]["audio_path"] == "candidate-part-2.wav"
    assert queue.candidate(candidate)["status"] == "approved"


def test_discarded_candidate_never_replaces_part(tmp_path):
    queue = NarrationQueue(tmp_path / "queue.sqlite3")
    job = queue.enqueue("Texto", "voz", "voxcpm2", ["Parte 1"])
    candidate = queue.stage_candidate(job["id"], 0, "new.wav")
    queue.discard_candidate(candidate)
    assert queue.get(job["id"])["parts"][0]["audio_path"] is None
    assert queue.candidate(candidate)["status"] == "discarded"


def test_queue_pause_blocks_new_jobs_until_resumed(tmp_path):
    queue = NarrationQueue(tmp_path / "queue.sqlite3")
    job = queue.enqueue("Texto", "voz", "voxcpm2", ["Parte"])
    queue.set_paused(True)
    assert queue.is_paused() is True
    assert queue.claim_next() is None
    queue.set_paused(False)
    assert queue.is_paused() is False
    assert queue.claim_next()["id"] == job["id"]


def test_queued_jobs_can_be_reordered_and_removed(tmp_path):
    queue = NarrationQueue(tmp_path / "queue.sqlite3")
    first = queue.enqueue("Texto 1", "voz", "voxcpm2", ["Parte 1"])
    second = queue.enqueue("Texto 2", "voz", "voxcpm2", ["Parte 2"])
    third = queue.enqueue("Texto 3", "voz", "voxcpm2", ["Parte 3"])

    queue.move(third["id"], "up")
    assert [job["id"] for job in queue.list_jobs() if job["status"] == "queued"] == [
        first["id"], third["id"], second["id"]
    ]
    queue.move(first["id"], "down")
    assert [job["id"] for job in queue.list_jobs() if job["status"] == "queued"] == [
        third["id"], first["id"], second["id"]
    ]
    assert queue.remove_queued(first["id"]) is True
    assert queue.get(first["id"]) is None
    assert queue.remove_queued(first["id"]) is False
