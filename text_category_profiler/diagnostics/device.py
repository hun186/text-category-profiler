"""Stable production classifier device observability."""


def report_classifier_device(torch_module, output=print):
    available = bool(torch_module.cuda.is_available())
    device = "cuda:0" if available else "cpu"
    output(
        f"TCF_CLASSIFIER_DEVICE device={device} "
        f"torch_cuda_available={available}"
    )
    gpu_name = None
    if available:
        gpu_name = torch_module.cuda.get_device_name(0)
        output(f"TCF_CLASSIFIER_GPU name={gpu_name}")
    return device, gpu_name
