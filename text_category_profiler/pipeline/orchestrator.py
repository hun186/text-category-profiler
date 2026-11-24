"""Dependency-light sequencing for the canonical root pipeline."""


class PipelineOrchestrator:
    """Run pipeline ports in their legacy order and under legacy conditions."""

    def __init__(
        self,
        context,
        *,
        convert,
        classify,
        combine,
        visualize,
        merge,
        deliver,
    ):
        self.context = context
        self.convert = convert
        self.classify = classify
        self.combine = combine
        self.visualize = visualize
        self.merge = merge
        self.deliver = deliver

    @staticmethod
    def _run_named_stage(name, invoke):
        """Preserve an error's identity while marking its failing stage.

        No automatic replay, rollback, file writes or private work identifiers.
        Python versions without Exception.add_note keep legacy propagation.
        """
        try:
            return invoke()
        except Exception as error:
            # Provenance is diagnostic only. Exception subclasses can expose
            # broken custom add_note/__notes__ implementations; those must
            # never replace the original stage failure or trigger any replay.
            try:
                note = "TCP_PIPELINE_FAILED_STAGE=" + name
                add_note = getattr(error, "add_note", None)
                if (callable(add_note)
                        and note not in getattr(error, "__notes__", ())):
                    add_note(note)
            except Exception:
                pass
            raise

    def run(self):
        self._run_named_stage("convert", self.convert)
        self._run_named_stage("classify", self.classify)
        if self.context.args.test is not True:
            return
        self._run_named_stage("combine", self.combine)
        self._run_named_stage("visualize", self.visualize)
        if self.context.args.task in ("SDSMS", "SDSMS_Prediction"):
            self._run_named_stage("merge", self.merge)
        self._run_named_stage("deliver", self.deliver)
