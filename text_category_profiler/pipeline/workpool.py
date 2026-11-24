"""WorkPool acquisition and delivery lifecycle boundaries."""

import os
from dataclasses import dataclass


_WINDOWS_RESERVED_DOS_DEVICE_BASES = frozenset({
    "CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$",
})
_WINDOWS_RESERVED_DOS_PORT_PREFIXES = frozenset({"COM", "LPT"})
# Windows also treats superscript 1, 2, 3 as device-port digits.
_WINDOWS_RESERVED_DOS_PORT_DIGITS = frozenset("123456789¹²³")


def is_windows_device_work_id(work_id):
    """Check Windows device aliases, even when an extension is appended.

    This is a lexical check only. Callers must also validate child-name
    grammar and must not attempt to open filesystem paths before validation.
    """
    if not isinstance(work_id, str):
        return False
    basename = work_id.split(".", 1)[0].rstrip(" ").upper()
    return (
        basename in _WINDOWS_RESERVED_DOS_DEVICE_BASES
        or (
            len(basename) == 4
            and basename[:3] in _WINDOWS_RESERVED_DOS_PORT_PREFIXES
            and basename[3] in _WINDOWS_RESERVED_DOS_PORT_DIGITS
        )
    )


def validate_external_work_id(work_id):
    """Require one portable, literal child name before any WorkPool side effect.

    IDs may include Unicode or interior spaces, but must never be interpreted
    as a path, Windows drive/ADS name, or platform-normalized alias. The empty
    string is handled by callers as the existing no-external-work mode.
    """
    if (
        not isinstance(work_id, str)
        or not work_id
        or work_id in (".", "..")
        or "/" in work_id
        or "\\" in work_id
        or ":" in work_id
        or work_id.endswith((".", " "))
        or is_windows_device_work_id(work_id)
        or any(ord(char) < 32 or ord(char) == 127 for char in work_id)
    ):
        raise ValueError("EXTERNAL_WORK_ID_INVALID")
    return work_id


@dataclass(frozen=True)
class WorkItemRecoveryObservation:
    """Safe-only interpretation of supplied WorkPool location metadata.

    Observation is NOT a claim of liveness, completed artifacts, ownership,
    quiescence, durability or permission to start/restart/relabel a job.
    """
    status: str
    observed_locations: tuple
    observations_complete: bool
    requires_operator_review: bool = True
    automatic_retry_authorized: bool = False
    delivery_verified: bool = False


def classify_external_work_item_locations(
        work_id, *, incoming, processing, processed):
    """Classify *supplied* three-valued metadata without touching a WorkPool.

    Values must be bool or None (unknown). A location can exist while it is
    still being written, stale, incomplete, aliased, or owned by another run.
    No outcome can authorize retry, cleanup or return completed reports.
    """
    validate_external_work_id(work_id)
    evidence = {
        "incoming": incoming,
        "processing": processing,
        "processed": processed,
    }
    if any(value is not None and type(value) is not bool
           for value in evidence.values()):
        raise TypeError("WORKITEM_RECOVERY_OBSERVATION_NOT_BOOLEAN")
    present = tuple(name for name, value in evidence.items() if value is True)
    complete = all(value is not None for value in evidence.values())
    if len(present) > 1:
        status = "MULTIPLE_LOCATIONS"
    elif not complete:
        status = "INCOMPLETE_OBSERVATION"
    elif not present:
        status = "NO_LOCATION_OBSERVED"
    else:
        status = present[0].upper() + "_ONLY"
    return WorkItemRecoveryObservation(
        status=status,
        observed_locations=present,
        observations_complete=complete,
    )


@dataclass(frozen=True)
class WorkPoolPlan:
    incoming_path: str
    pool_path: str
    work_id: str
    remove_dataset: bool
    task: str
    workpool_root: str
    output_patterns: tuple

    @classmethod
    def from_context(cls, context, *, workpool_root):
        args = context.args
        return cls(
            incoming_path=args.WeiTechworkIDPath,
            pool_path=args.WeiTechWorkPoolPATH,
            work_id=args.WeiTechworkID,
            remove_dataset=args.RemoveBertDataDir,
            task=args.task,
            workpool_root=workpool_root,
            output_patterns=tuple(context.final_output_patterns),
        )

    def with_work_id(self, work_id):
        return WorkPoolPlan(
            incoming_path=self.incoming_path,
            pool_path=self.pool_path,
            work_id=work_id,
            remove_dataset=self.remove_dataset,
            task=self.task,
            workpool_root=self.workpool_root,
            output_patterns=self.output_patterns,
        )


class WorkPoolManager:
    def __init__(self, plan, filesystem, *, warning=None, info=None):
        self.plan = plan
        self.filesystem = filesystem
        self.warning = warning or (lambda message: None)
        self.info = info or (lambda message: None)

    def acquire(self):
        # A preselected ID can originate in CLI configuration rather than
        # os.listdir; validate it before even inspecting external directories.
        if self.plan.work_id != "":
            validate_external_work_id(self.plan.work_id)
        candidates = sorted(
            self.filesystem.list_directory(self.plan.incoming_path), reverse=True
        )
        if not candidates:
            self.warning(
                f"WeiTechworkIDPath is set as {self.plan.incoming_path}, "
                "but there is no WTwork To Run. Abort!"
            )
            raise Exception()

        available = self.filesystem.list_directory(self.plan.pool_path)
        selected_work_id = self.plan.work_id
        for work_id in candidates:
            # A caller-specified external ID must never acquire another
            # work item simply because it sorts newer. Retain legacy behavior
            # when no ID is specified (latest matching WorkPool entry).
            if selected_work_id and work_id != selected_work_id:
                continue
            if work_id in available:
                # Validate selected listdir entries before creating the
                # processing parent or moving any work-ID directory.
                validate_external_work_id(work_id)
                processing = os.path.join(
                    self.plan.incoming_path, "..", "AutoBertClassify_Processing"
                )
                self.filesystem.make_directory(processing)
                self.filesystem.move(
                    os.path.join(self.plan.incoming_path, work_id),
                    os.path.join(processing, work_id),
                )
                selected_work_id = work_id
                break
        else:
            # An explicitly requested external job must be claimed from
            # incoming, not silently carried forward from a prior run.
            # Otherwise the pipeline may process/backup/deliver another job
            # without any successful incoming -> processing handoff.
            if self.plan.work_id:
                raise RuntimeError("EXTERNAL_WORK_ID_NOT_CLAIMED")
            # With external mode configured, zero matches is not permission
            # to run a generic dataset pipeline without a claimed work item.
            raise RuntimeError("EXTERNAL_WORKPOOL_NO_MATCH")
        self.info(
            f"Found workID {selected_work_id} in {self.plan.incoming_path}, "
            "we will start to apply this task."
        )
        return selected_work_id


class DeliveryManager:
    def __init__(self, plan, filesystem, *, output_logger=None,
                 move_error_reporter=None):
        self.plan = plan
        self.filesystem = filesystem
        self.output_logger = output_logger or (lambda message: None)
        self.move_error_reporter = move_error_reporter or print

    def backup_and_complete(self, dataset_dir):
        # Fail before optional cleanup-backup, per-work-ID backup, chown,
        # logging or final move. An empty ID remains the legacy no-job mode.
        if self.plan.work_id != "":
            validate_external_work_id(self.plan.work_id)
        if self.plan.remove_dataset is True:
            self.filesystem.backup(
                WorkPoolROOT=self.plan.workpool_root,
                BertDatasetSubDir=dataset_dir,
            )

        if self.plan.work_id == "":
            return

        destination = os.path.join(self.plan.pool_path, self.plan.work_id)
        patterns = list(self.plan.output_patterns)
        if (
            self.plan.task in ("SDSMS", "SDSMS_Prediction")
            and "SDSMS.*" not in patterns
        ):
            patterns.append("SDSMS.*")
        self.filesystem.backup(
            BertDatasetSubDir=dataset_dir,
            DesDir=destination,
            BackFNrePatList=patterns,
        )
        completion_message = (
            f"Complete {self.plan.incoming_path}/{self.plan.work_id}, Move Output "
            f"{dataset_dir}/DFPreambleCols_df_ALL.sql3 to {destination}"
        )

        processing = os.path.join(
            self.plan.incoming_path, "..", "AutoBertClassify_Processing"
        )
        processed = os.path.join(
            self.plan.incoming_path, "..", "AutoBertClassify_Processed"
        )
        source = os.path.join(processing, self.plan.work_id)
        completed = os.path.join(processed, self.plan.work_id)

        # Create the parent before Linux ownership changes. Never inspect
        # or chown a pre-existing completed/<work-id> here: it can belong to
        # another run and the exclusive move may still fail with a collision.
        self.filesystem.make_directory(processed)
        linux_ownership = "linux" in self.filesystem.platform_name().lower()
        if linux_ownership:
            for path in (processing, processed, source):
                self.filesystem.chown(path)
        try:
            self.filesystem.move(source, completed)
        except Exception as error:
            # An external job is NOT complete if its processing -> processed
            # handoff failed. Report it, but preserve the original exception
            # even when the diagnostic callback itself is broken.
            try:
                self.move_error_reporter(error)
            except Exception:
                pass
            raise

        # Only after successful exclusive move is completed/<work-id> this
        # run's directory. Apply descendant ownership now; a failure here is
        # post-commit and must not trigger a replay of the non-idempotent move.
        if linux_ownership:
            try:
                for path in self.filesystem.walk(completed):
                    self.filesystem.chown(path)
            except Exception as error:
                try:
                    self.move_error_reporter(error)
                except Exception:
                    pass

        # The move has committed; the earlier backup and this move are
        # separate operations, not one atomic transaction. Do not report
        # "Complete" prematurely. Conversely, a logging failure after the
        # move must never replay this non-idempotent handoff.
        try:
            self.output_logger(completion_message)
        except Exception as error:
            try:
                self.move_error_reporter(error)
            except Exception:
                pass
