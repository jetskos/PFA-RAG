"""
Tests — DjangoCheckpointSaver

Vérifie que les checkpoints LangGraph sont bien persistés, récupérés et listés
via l'ORM Django (GraphCheckpoint, GraphWrite).

Run : python manage.py test tuteur_ia.tests.test_checkpointer
"""
import uuid
from unittest.mock import MagicMock, patch

from django.test import TestCase

from tuteur_ia.models import GraphCheckpoint, GraphWrite


def _make_checkpoint(cid: str = None) -> dict:
    return {
        "id": cid or str(uuid.uuid4()),
        "v": 1,
        "ts": "2024-01-01T00:00:00+00:00",
        "channel_values": {"messages": []},
        "channel_versions": {},
        "versions_seen": {},
        "pending_sends": [],
    }


def _make_config(thread_id: str, checkpoint_id: str = None, checkpoint_ns: str = "") -> dict:
    c = {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns}
    if checkpoint_id:
        c["checkpoint_id"] = checkpoint_id
    return {"configurable": c}


class DjangoCheckpointSaverTest(TestCase):

    def setUp(self):
        from tuteur_ia.graph.checkpointer import DjangoCheckpointSaver
        self.saver = DjangoCheckpointSaver()
        self.thread_id = str(uuid.uuid4())

    # ── put / get_tuple ───────────────────────────────────────────────────────

    def test_put_creates_row(self):
        ckpt = _make_checkpoint()
        config = _make_config(self.thread_id)
        self.saver.put(config, ckpt, {"source": "loop", "step": 1, "writes": {}}, {})

        self.assertEqual(
            GraphCheckpoint.objects.filter(thread_id=self.thread_id).count(), 1
        )

    def test_get_tuple_returns_latest(self):
        ckpt1 = _make_checkpoint()
        ckpt2 = _make_checkpoint()
        config = _make_config(self.thread_id)

        self.saver.put(config, ckpt1, {"source": "loop", "step": 1, "writes": {}}, {})
        self.saver.put(
            _make_config(self.thread_id, ckpt1["id"]),
            ckpt2,
            {"source": "loop", "step": 2, "writes": {}},
            {},
        )

        result = self.saver.get_tuple(_make_config(self.thread_id))
        self.assertIsNotNone(result)
        self.assertEqual(result.checkpoint["id"], ckpt2["id"])

    def test_get_tuple_by_id(self):
        ckpt = _make_checkpoint()
        config = _make_config(self.thread_id)
        out_config = self.saver.put(config, ckpt, {"source": "loop", "step": 1, "writes": {}}, {})

        checkpoint_id = out_config["configurable"]["checkpoint_id"]
        result = self.saver.get_tuple(_make_config(self.thread_id, checkpoint_id))
        self.assertIsNotNone(result)
        self.assertEqual(result.checkpoint["id"], ckpt["id"])

    def test_get_tuple_returns_none_for_unknown_thread(self):
        result = self.saver.get_tuple(_make_config("unknown-thread"))
        self.assertIsNone(result)

    def test_put_is_idempotent(self):
        """Mettre deux fois le même checkpoint_id → toujours 1 ligne."""
        ckpt = _make_checkpoint()
        config = _make_config(self.thread_id)
        meta = {"source": "loop", "step": 1, "writes": {}}
        self.saver.put(config, ckpt, meta, {})
        self.saver.put(config, ckpt, meta, {})
        self.assertEqual(
            GraphCheckpoint.objects.filter(thread_id=self.thread_id).count(), 1
        )

    # ── list ──────────────────────────────────────────────────────────────────

    def test_list_returns_all_checkpoints(self):
        ckpt1 = _make_checkpoint()
        ckpt2 = _make_checkpoint()
        config = _make_config(self.thread_id)
        meta = {"source": "loop", "step": 1, "writes": {}}
        self.saver.put(config, ckpt1, meta, {})
        self.saver.put(_make_config(self.thread_id, ckpt1["id"]), ckpt2, meta, {})

        results = list(self.saver.list(_make_config(self.thread_id)))
        self.assertEqual(len(results), 2)

    def test_list_with_limit(self):
        for _ in range(4):
            ckpt = _make_checkpoint()
            config = _make_config(self.thread_id)
            self.saver.put(config, ckpt, {"source": "loop", "step": 1, "writes": {}}, {})

        results = list(self.saver.list(_make_config(self.thread_id), limit=2))
        self.assertEqual(len(results), 2)

    def test_list_returns_empty_for_unknown_thread(self):
        results = list(self.saver.list(_make_config("no-such-thread")))
        self.assertEqual(results, [])

    # ── put_writes ────────────────────────────────────────────────────────────

    def test_put_writes_creates_rows(self):
        ckpt = _make_checkpoint()
        config = _make_config(self.thread_id)
        out_config = self.saver.put(config, ckpt, {"source": "loop", "step": 1, "writes": {}}, {})

        self.saver.put_writes(
            out_config,
            [("messages", [{"type": "human", "content": "Bonjour"}])],
            task_id="task-1",
        )

        self.assertEqual(
            GraphWrite.objects.filter(thread_id=self.thread_id).count(), 1
        )

    def test_get_tuple_includes_pending_writes(self):
        ckpt = _make_checkpoint()
        config = _make_config(self.thread_id)
        out_config = self.saver.put(config, ckpt, {"source": "loop", "step": 1, "writes": {}}, {})

        self.saver.put_writes(
            out_config,
            [("channel_a", "valeur_test")],
            task_id="task-42",
        )

        result = self.saver.get_tuple(out_config)
        self.assertEqual(len(result.pending_writes), 1)
        task_id, channel, value = result.pending_writes[0]
        self.assertEqual(channel, "channel_a")
        self.assertEqual(value, "valeur_test")

    # ── parent_config ─────────────────────────────────────────────────────────

    def test_parent_config_is_set(self):
        ckpt1 = _make_checkpoint()
        ckpt2 = _make_checkpoint()
        config = _make_config(self.thread_id)
        meta = {"source": "loop", "step": 1, "writes": {}}

        out1 = self.saver.put(config, ckpt1, meta, {})
        self.saver.put(out1, ckpt2, meta, {})

        result = self.saver.get_tuple(_make_config(self.thread_id))
        self.assertIsNotNone(result.parent_config)
        self.assertEqual(
            result.parent_config["configurable"]["checkpoint_id"], ckpt1["id"]
        )
