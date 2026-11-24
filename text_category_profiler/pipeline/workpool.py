"""WorkPool acquisition and delivery lifecycle boundaries."""

import os
from dataclasses import dataclass


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
        or any(ord(char) < 32 or ord(char) == 127 for char in work_id)
    ):
        raise ValueError("EXTERNAL_WORK_ID_INVALID")
    return work_id


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

        if "linux" in self.filesystem.platform_name().lower():
            for path in [processing, processed, source] + self.filesystem.walk(completed):
                self.filesystem.chown(path)

        self.filesystem.make_directory(processed)
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
