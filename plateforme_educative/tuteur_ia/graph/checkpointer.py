"""
DjangoCheckpointSaver — Persistance LangGraph via Django ORM (MySQL).

Remplace MemorySaver() : les checkpoints survivent aux redémarrages du serveur.
Utilise JsonPlusSerializer (pas de pickle) pour la sécurité.

Modèles Django utilisés :
  - GraphCheckpoint : snapshots complets du workflow
  - GraphWrite      : pending writes entre nœuds (interrupt_after)
"""
import json
import logging
from typing import Any, Iterator, Optional, Sequence, Tuple

from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    CheckpointTuple,
    ChannelVersions,
)

logger = logging.getLogger(__name__)

# Metadata est toujours un dict JSON simple — on sérialise directement
# sans passer par serde pour éviter les incompatibilités de type (msgpack vs json).
def _dump_meta(meta: dict) -> bytes:
    return json.dumps(meta, default=str).encode("utf-8")

def _load_meta(data: bytes) -> dict:
    return json.loads(data.decode("utf-8"))


def _get_serde():
    try:
        from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
        return JsonPlusSerializer()
    except ImportError:
        from langgraph.checkpoint.base import JsonPlusSerializer
        return JsonPlusSerializer()


class DjangoCheckpointSaver(BaseCheckpointSaver):
    """
    Checkpointer LangGraph sauvegardant dans la base Django (MySQL).

    Usage :
        checkpointer = DjangoCheckpointSaver()
        graph = workflow.compile(checkpointer=checkpointer, ...)
    """

    def __init__(self):
        super().__init__(serde=_get_serde())

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _configurable(self, config: dict) -> Tuple[str, str, Optional[str]]:
        c = config.get("configurable", {})
        return (
            c["thread_id"],
            c.get("checkpoint_ns", ""),
            c.get("checkpoint_id"),
        )

    def _build_config(self, thread_id: str, checkpoint_ns: str, checkpoint_id: str) -> dict:
        return {
            "configurable": {
                "thread_id":     thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
        }

    def _row_to_tuple(self, obj, thread_id: str, checkpoint_ns: str) -> CheckpointTuple:
        from tuteur_ia.models import GraphWrite

        checkpoint = self.serde.loads_typed((obj.type, bytes(obj.checkpoint)))
        metadata   = _load_meta(bytes(obj.metadata))

        config = self._build_config(thread_id, checkpoint_ns, obj.checkpoint_id)
        parent_config = (
            self._build_config(thread_id, checkpoint_ns, obj.parent_checkpoint_id)
            if obj.parent_checkpoint_id else None
        )

        # `list(...)` force la consommation immédiate du curseur : sous SQLite,
        # un queryset itéré paresseusement laisse un curseur ouvert qui verrouille
        # la base pour toute écriture ultérieure de la même connexion
        # (« database is locked » dans la vue repondre).
        writes_qs = list(GraphWrite.objects.filter(
            thread_id=thread_id,
            checkpoint_ns=checkpoint_ns,
            checkpoint_id=obj.checkpoint_id,
        ).order_by("task_id", "idx"))

        pending_writes = []
        for w in writes_qs:
            try:
                val = self.serde.loads_typed((w.type, bytes(w.value)))
                pending_writes.append((w.task_id, w.channel, val))
            except Exception as e:
                logger.warning(f"Échec désérialisation write {w.pk} : {e}")

        return CheckpointTuple(
            config=config,
            checkpoint=checkpoint,
            metadata=metadata,
            parent_config=parent_config,
            pending_writes=pending_writes,
        )

    # ── BaseCheckpointSaver API ───────────────────────────────────────────────

    def get_tuple(self, config: dict) -> Optional[CheckpointTuple]:
        from tuteur_ia.models import GraphCheckpoint

        thread_id, checkpoint_ns, checkpoint_id = self._configurable(config)

        try:
            if checkpoint_id:
                obj = GraphCheckpoint.objects.get(
                    thread_id=thread_id,
                    checkpoint_ns=checkpoint_ns,
                    checkpoint_id=checkpoint_id,
                )
            else:
                obj = (
                    GraphCheckpoint.objects
                    .filter(thread_id=thread_id, checkpoint_ns=checkpoint_ns)
                    .order_by("-created_at")
                    .first()
                )
                if obj is None:
                    return None

            return self._row_to_tuple(obj, thread_id, checkpoint_ns)

        except GraphCheckpoint.DoesNotExist:
            return None
        except Exception as e:
            logger.error(f"get_tuple error : {e}", exc_info=True)
            return None

    def list(
        self,
        config: Optional[dict],
        *,
        filter: Optional[dict] = None,
        before: Optional[dict] = None,
        limit: Optional[int] = None,
    ) -> Iterator[CheckpointTuple]:
        from tuteur_ia.models import GraphCheckpoint

        if config is None:
            return

        thread_id, checkpoint_ns, _ = self._configurable(config)

        qs = GraphCheckpoint.objects.filter(
            thread_id=thread_id,
            checkpoint_ns=checkpoint_ns,
        ).order_by("-created_at")

        if before is not None:
            before_id = before.get("configurable", {}).get("checkpoint_id")
            if before_id:
                try:
                    before_obj = GraphCheckpoint.objects.get(
                        thread_id=thread_id,
                        checkpoint_ns=checkpoint_ns,
                        checkpoint_id=before_id,
                    )
                    qs = qs.filter(created_at__lt=before_obj.created_at)
                except GraphCheckpoint.DoesNotExist:
                    pass

        if limit is not None:
            qs = qs[:limit]

        # Matérialiser avant de `yield` : ne pas garder un curseur SQLite ouvert
        # pendant que l'appelant (LangGraph) consomme le générateur — sinon toute
        # écriture concurrente échoue avec « database is locked ».
        for obj in list(qs):
            try:
                yield self._row_to_tuple(obj, thread_id, checkpoint_ns)
            except Exception as e:
                logger.warning(f"list: skip checkpoint {obj.checkpoint_id[:8]} : {e}")

    def put(
        self,
        config: dict,
        checkpoint: dict,
        metadata: dict,
        new_versions: ChannelVersions,
    ) -> dict:
        from tuteur_ia.models import GraphCheckpoint

        thread_id, checkpoint_ns, parent_id = self._configurable(config)
        checkpoint_id = checkpoint["id"]

        try:
            type_, ckpt_bytes = self.serde.dumps_typed(checkpoint)
            meta_bytes        = _dump_meta(metadata)
        except Exception as e:
            logger.error(f"put: sérialisation échouée : {e}")
            raise

        GraphCheckpoint.objects.update_or_create(
            thread_id=thread_id,
            checkpoint_ns=checkpoint_ns,
            checkpoint_id=checkpoint_id,
            defaults={
                "parent_checkpoint_id": parent_id or None,
                "type":       type_,
                "checkpoint": ckpt_bytes,
                "metadata":   meta_bytes,
            },
        )

        logger.debug(
            f"Checkpoint sauvegardé : thread={thread_id[:8]} id={checkpoint_id[:8]}"
        )

        return self._build_config(thread_id, checkpoint_ns, checkpoint_id)

    def put_writes(
        self,
        config: dict,
        writes: Sequence[Tuple[str, Any]],
        task_id: str,
    ) -> None:
        from tuteur_ia.models import GraphWrite

        thread_id, checkpoint_ns, checkpoint_id = self._configurable(config)
        if not checkpoint_id:
            logger.warning("put_writes appelé sans checkpoint_id dans config")
            return

        for idx, (channel, value) in enumerate(writes):
            try:
                type_, val_bytes = self.serde.dumps_typed(value)
                GraphWrite.objects.update_or_create(
                    thread_id=thread_id,
                    checkpoint_ns=checkpoint_ns,
                    checkpoint_id=checkpoint_id,
                    task_id=task_id,
                    idx=idx,
                    defaults={
                        "channel": channel,
                        "type":    type_,
                        "value":   val_bytes,
                    },
                )
            except Exception as e:
                logger.error(f"put_writes channel={channel} idx={idx} : {e}")
