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

    def run(self):
        self.convert()
        self.classify()
        if self.context.args.test is not True:
            return
        self.combine()
        self.visualize()
        if self.context.args.task in ("SDSMS", "SDSMS_Prediction"):
            self.merge()
        self.deliver()
