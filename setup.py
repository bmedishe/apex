import torch
from torch.utils.cpp_extension import BuildExtension, CppExtension, CUDAExtension, CUDA_HOME
from setuptools import setup, find_packages
import subprocess

import sys
import warnings
import os

# ninja build does not work unless include_dirs are abs path
this_dir = os.path.dirname(os.path.abspath(__file__))

def get_cuda_bare_metal_version(cuda_dir):
    raw_output = subprocess.check_output([cuda_dir + "/bin/nvcc", "-V"], universal_newlines=True)
    output = raw_output.split()
    release_idx = output.index("release") + 1
    release = output[release_idx].split(".")
    bare_metal_major = release[0]
    bare_metal_minor = release[1][0]

    return raw_output, bare_metal_major, bare_metal_minor

print("\n\ntorch.__version__  = {}\n\n".format(torch.__version__))
TORCH_MAJOR = int(torch.__version__.split('.')[0])
TORCH_MINOR = int(torch.__version__.split('.')[1])

def check_if_rocm_pytorch():
    is_rocm_pytorch = False
    if TORCH_MAJOR > 1 or (TORCH_MAJOR == 1 and TORCH_MINOR >= 5):
        from torch.utils.cpp_extension import ROCM_HOME
        is_rocm_pytorch = True if ((torch.version.hip is not None) and (ROCM_HOME is not None)) else False

    return is_rocm_pytorch

IS_ROCM_PYTORCH = check_if_rocm_pytorch()

if not torch.cuda.is_available() and not IS_ROCM_PYTORCH:
    # https://github.com/NVIDIA/apex/issues/486
    # Extension builds after https://github.com/pytorch/pytorch/pull/23408 attempt to query torch.cuda.get_device_capability(),
    # which will fail if you are compiling in an environment without visible GPUs (e.g. during an nvidia-docker build command).
    print('\nWarning: Torch did not find available GPUs on this system.\n',
          'If your intention is to cross-compile, this is not an error.\n'
          'By default, Apex will cross-compile for Pascal (compute capabilities 6.0, 6.1, 6.2),\n'
          'Volta (compute capability 7.0), Turing (compute capability 7.5),\n'
          'and, if the CUDA version is >= 11.0, Ampere (compute capability 8.0).\n'
          'If you wish to cross-compile for a single specific architecture,\n'
          'export TORCH_CUDA_ARCH_LIST="compute capability" before running setup.py.\n')
    if os.environ.get("TORCH_CUDA_ARCH_LIST", None) is None:
        _, bare_metal_major, _ = get_cuda_bare_metal_version(CUDA_HOME)
        if int(bare_metal_major) == 11:
            os.environ["TORCH_CUDA_ARCH_LIST"] = "6.0;6.1;6.2;7.0;7.5;8.0"
        else:
            os.environ["TORCH_CUDA_ARCH_LIST"] = "6.0;6.1;6.2;7.0;7.5"
elif not torch.cuda.is_available() and IS_ROCM_PYTORCH:
    print('\nWarning: Torch did not find available GPUs on this system.\n',
          'If your intention is to cross-compile, this is not an error.\n'
          'By default, Apex will cross-compile for the same gfx targets\n'
          'used by default in ROCm PyTorch\n')

if TORCH_MAJOR == 0 and TORCH_MINOR < 4:
      raise RuntimeError("Apex requires Pytorch 0.4 or newer.\n" +
                         "The latest stable release can be obtained from https://pytorch.org/")

cmdclass = {}
ext_modules = []

extras = {}
if "--pyprof" in sys.argv:
    string = "\n\nPyprof has been moved to its own dedicated repository and will " + \
             "soon be removed from Apex.  Please visit\n" + \
             "https://github.com/NVIDIA/PyProf\n" + \
             "for the latest version."
    warnings.warn(string, DeprecationWarning)
    with open('requirements.txt') as f:
        required_packages = f.read().splitlines()
        extras['pyprof'] = required_packages
    try:
        sys.argv.remove("--pyprof")
    except:
        pass
else:
    warnings.warn("Option --pyprof not specified. Not installing PyProf dependencies!")

if "--cpp_ext" in sys.argv or "--cuda_ext" in sys.argv:
    if TORCH_MAJOR == 0:
        raise RuntimeError("--cpp_ext requires Pytorch 1.0 or later, "
                           "found torch.__version__ = {}".format(torch.__version__))
    cmdclass['build_ext'] = BuildExtension
if "--cpp_ext" in sys.argv:
    sys.argv.remove("--cpp_ext")
    ext_modules.append(
        CppExtension('apex_C',
                     ['csrc/flatten_unflatten.cpp',]))

def get_cuda_bare_metal_version(cuda_dir):
    raw_output = subprocess.check_output([cuda_dir + "/bin/nvcc", "-V"], universal_newlines=True)
    output = raw_output.split()
    release_idx = output.index("release") + 1
    release = output[release_idx].split(".")
    bare_metal_major = release[0]
    bare_metal_minor = release[1][0]

    return raw_output, bare_metal_major, bare_metal_minor

def check_cuda_torch_binary_vs_bare_metal(cuda_dir):
    raw_output, bare_metal_major, bare_metal_minor = get_cuda_bare_metal_version(cuda_dir)
    torch_binary_major = torch.version.cuda.split(".")[0]
    torch_binary_minor = torch.version.cuda.split(".")[1]

    print("\nCompiling cuda extensions with")
    print(raw_output + "from " + cuda_dir + "/bin\n")

    if (bare_metal_major != torch_binary_major) or (bare_metal_minor != torch_binary_minor):
        raise RuntimeError("Cuda extensions are being compiled with a version of Cuda that does " +
                           "not match the version used to compile Pytorch binaries.  " +
                           "Pytorch binaries were compiled with Cuda {}.\n".format(torch.version.cuda) +
                           "In some cases, a minor-version mismatch will not cause later errors:  " +
                           "https://github.com/NVIDIA/apex/pull/323#discussion_r287021798.  "
                           "You can try commenting out this check (at your own risk).")

# Set up macros for forward/backward compatibility hack around
# https://github.com/pytorch/pytorch/commit/4404762d7dd955383acee92e6f06b48144a0742e
# and
# https://github.com/NVIDIA/apex/issues/456
# https://github.com/pytorch/pytorch/commit/eb7b39e02f7d75c26d8a795ea8c7fd911334da7e#diff-4632522f237f1e4e728cb824300403ac
version_ge_1_1 = []
if (TORCH_MAJOR > 1) or (TORCH_MAJOR == 1 and TORCH_MINOR > 0):
    version_ge_1_1 = ['-DVERSION_GE_1_1']
version_ge_1_3 = []
if (TORCH_MAJOR > 1) or (TORCH_MAJOR == 1 and TORCH_MINOR > 2):
    version_ge_1_3 = ['-DVERSION_GE_1_3']
version_ge_1_5 = []
if (TORCH_MAJOR > 1) or (TORCH_MAJOR == 1 and TORCH_MINOR > 4):
    version_ge_1_5 = ['-DVERSION_GE_1_5']
version_dependent_macros = version_ge_1_1 + version_ge_1_3 + version_ge_1_5

if "--distributed_adam" in sys.argv or "--cuda_ext" in sys.argv:
    from torch.utils.cpp_extension import CUDAExtension
    if "--distributed_adam" in sys.argv:
        sys.argv.remove("--distributed_adam")

    from torch.utils.cpp_extension import BuildExtension
    cmdclass['build_ext'] = BuildExtension

    if torch.utils.cpp_extension.CUDA_HOME is None and not IS_ROCM_PYTORCH:
        raise RuntimeError("--distributed_adam was requested, but nvcc was not found.  Are you sure your environment has nvcc available?  If you're installing within a container from https://hub.docker.com/r/pytorch/pytorch, only images whose names contain 'devel' will provide nvcc.")
    else:
        nvcc_args_adam = ['-O3', '--use_fast_math'] + version_dependent_macros
        hipcc_args_adam = ['-O3'] + version_dependent_macros
        ext_modules.append(
            CUDAExtension(name='distributed_adam_cuda',
                          sources=['apex/contrib/csrc/optimizers/multi_tensor_distopt_adam.cpp',
                                   'apex/contrib/csrc/optimizers/multi_tensor_distopt_adam_kernel.cu'],
                          include_dirs=[os.path.join(this_dir, 'csrc'),
                                        os.path.join(this_dir, 'apex/contrib/csrc/optimizers')],
                          extra_compile_args={'cxx': ['-O3',] + version_dependent_macros,
                                              'nvcc':nvcc_args_adam if not IS_ROCM_PYTORCH else hipcc_args_adam}))

if "--distributed_lamb" in sys.argv or "--cuda_ext" in sys.argv:
    from torch.utils.cpp_extension import CUDAExtension
    if "--distributed_lamb" in sys.argv:
        sys.argv.remove("--distributed_lamb")

    from torch.utils.cpp_extension import BuildExtension
    cmdclass['build_ext'] = BuildExtension

    if torch.utils.cpp_extension.CUDA_HOME is None and not IS_ROCM_PYTORCH:
        raise RuntimeError("--distributed_lamb was requested, but nvcc was not found.  Are you sure your environment has nvcc available?  If you're installing within a container from https://hub.docker.com/r/pytorch/pytorch, only images whose names contain 'devel' will provide nvcc.")
    else:
        print ("INFO: Building the distributed_lamb extension.")
        nvcc_args_distributed_lamb = ['-O3', '--use_fast_math'] + version_dependent_macros
        hipcc_args_distributed_lamb = ['-O3'] + version_dependent_macros
        ext_modules.append(
            CUDAExtension(name='distributed_lamb_cuda',
                          sources=['apex/contrib/csrc/optimizers/multi_tensor_distopt_lamb.cpp',
                                   'apex/contrib/csrc/optimizers/multi_tensor_distopt_lamb_kernel.cu'],
                          include_dirs=[os.path.join(this_dir, 'csrc')],
                          extra_compile_args={'cxx': ['-O3',] + version_dependent_macros,
                                              'nvcc': nvcc_args_distributed_lamb if not IS_ROCM_PYTORCH else hipcc_args_distributed_lamb}))

if "--cuda_ext" in sys.argv:
    from torch.utils.cpp_extension import CUDAExtension

    if torch.utils.cpp_extension.CUDA_HOME is None and not IS_ROCM_PYTORCH:
        raise RuntimeError("--cuda_ext was requested, but nvcc was not found.  Are you sure your environment has nvcc available?  If you're installing within a container from https://hub.docker.com/r/pytorch/pytorch, only images whose names contain 'devel' will provide nvcc.")
    else:
        if not IS_ROCM_PYTORCH:
            check_cuda_torch_binary_vs_bare_metal(torch.utils.cpp_extension.CUDA_HOME)

        print ("INFO: Building the multi-tensor apply extension.")
        nvcc_args_multi_tensor = ['-lineinfo', '-O3', '--use_fast_math'] + version_dependent_macros
        hipcc_args_multi_tensor = ['-O3'] + version_dependent_macros
        ext_modules.append(
            CUDAExtension(name='amp_C',
                          sources=['csrc/amp_C_frontend.cpp',
                                   'csrc/multi_tensor_sgd_kernel.cu',
                                   'csrc/multi_tensor_scale_kernel.cu',
                                   'csrc/multi_tensor_axpby_kernel.cu',
                                   'csrc/multi_tensor_l2norm_kernel.cu',
                                   'csrc/multi_tensor_l2norm_kernel_mp.cu',
                                   'csrc/multi_tensor_l2norm_scale_kernel.cu',
                                   'csrc/multi_tensor_lamb_stage_1.cu',
                                   'csrc/multi_tensor_lamb_stage_2.cu',
                                   'csrc/multi_tensor_adam.cu',
                                   'csrc/multi_tensor_adagrad.cu',
                                   'csrc/multi_tensor_novograd.cu',
                                   'csrc/multi_tensor_lamb.cu',
                                   'csrc/multi_tensor_lamb_mp.cu'],
                          include_dirs=[os.path.join(this_dir, 'csrc')],
                          extra_compile_args={'cxx': ['-O3'] + version_dependent_macros,
                                              'nvcc': nvcc_args_multi_tensor if not IS_ROCM_PYTORCH else hipcc_args_multi_tensor}))

        print ("INFO: Building syncbn extension.")
        ext_modules.append(
            CUDAExtension(name='syncbn',
                          sources=['csrc/syncbn.cpp',
                                   'csrc/welford.cu'],
                          include_dirs=[os.path.join(this_dir, 'csrc')],
                          extra_compile_args={'cxx': ['-O3'] + version_dependent_macros,
                                              'nvcc':['-O3'] + version_dependent_macros}))

        nvcc_args_layer_norm = ['-maxrregcount=50', '-O3', '--use_fast_math'] + version_dependent_macros
        hipcc_args_layer_norm = ['-O3'] + version_dependent_macros
        print ("INFO: Building fused layernorm extension.")
        ext_modules.append(
            CUDAExtension(name='fused_layer_norm_cuda',
                          sources=['csrc/layer_norm_cuda.cpp',
                                   'csrc/layer_norm_cuda_kernel.cu'],
                          include_dirs=[os.path.join(this_dir, 'csrc')],
                          extra_compile_args={'cxx': ['-O3'] + version_dependent_macros,
                                              'nvcc': nvcc_args_layer_norm if not IS_ROCM_PYTORCH else hipcc_args_layer_norm}))

        print ("INFO: Building the MLP Extension.")
        ext_modules.append(
            CUDAExtension(name='mlp_cuda',
                          sources=['csrc/mlp.cpp',
                                   'csrc/mlp_cuda.cu'],
                          include_dirs=[os.path.join(this_dir, 'csrc')],
                          extra_compile_args={'cxx': ['-O3'] + version_dependent_macros,
                                              'nvcc':['-O3'] + version_dependent_macros}))
        ext_modules.append(
            CUDAExtension(name='fused_dense_cuda',
                          sources=['csrc/fused_dense.cpp',
                                   'csrc/fused_dense_cuda.cu'],
                          extra_compile_args={'cxx': ['-O3'] + version_dependent_macros,
                                              'nvcc':['-O3'] + version_dependent_macros}))
        """
        ext_modules.append(
            CUDAExtension(name='scaled_upper_triang_masked_softmax_cuda',
                          sources=['csrc/megatron/scaled_upper_triang_masked_softmax.cpp',
                                   'csrc/megatron/scaled_upper_triang_masked_softmax_cuda.cu'],
                          include_dirs=[os.path.join(this_dir, 'csrc')],
                          extra_compile_args={'cxx': ['-O3'] + version_dependent_macros,
                                              'nvcc':['-O3',
                                                      '-U__CUDA_NO_HALF_OPERATORS__',
                                                      '-U__CUDA_NO_HALF_CONVERSIONS__',
                                                      '--expt-relaxed-constexpr',
                                                      '--expt-extended-lambda'] + version_dependent_macros}))

        ext_modules.append(
            CUDAExtension(name='scaled_masked_softmax_cuda',
                          sources=['csrc/megatron/scaled_masked_softmax.cpp',
                                   'csrc/megatron/scaled_masked_softmax_cuda.cu'],
                          include_dirs=[os.path.join(this_dir, 'csrc')],
                          extra_compile_args={'cxx': ['-O3'] + version_dependent_macros,
                                              'nvcc':['-O3',
                                                      '-U__CUDA_NO_HALF_OPERATORS__',
                                                      '-U__CUDA_NO_HALF_CONVERSIONS__',
                                                      '--expt-relaxed-constexpr',
                                                      '--expt-extended-lambda'] + version_dependent_macros}))
        """

if "--bnp" in sys.argv or "--cuda_ext" in sys.argv:
    from torch.utils.cpp_extension import CUDAExtension
    if "--bnp" in sys.argv:
        sys.argv.remove("--bnp")

    from torch.utils.cpp_extension import BuildExtension
    cmdclass['build_ext'] = BuildExtension

    if torch.utils.cpp_extension.CUDA_HOME is None and not IS_ROCM_PYTORCH:
        raise RuntimeError("--bnp was requested, but nvcc was not found.  Are you sure your environment has nvcc available?  If you're installing within a container from https://hub.docker.com/r/pytorch/pytorch, only images whose names contain 'devel' will provide nvcc.")
    else:
        ext_modules.append(
            CUDAExtension(name='bnp',
                          sources=['apex/contrib/csrc/groupbn/batch_norm.cu',
                                   'apex/contrib/csrc/groupbn/ipc.cu',
                                   'apex/contrib/csrc/groupbn/interface.cpp',
                                   'apex/contrib/csrc/groupbn/batch_norm_add_relu.cu'],
                          include_dirs=[os.path.join(this_dir, 'csrc'),
                                        os.path.join(this_dir, 'apex/contrib/csrc/groupbn')],
                          extra_compile_args={'cxx': [] + version_dependent_macros,
                                              'nvcc':['-DCUDA_HAS_FP16=1',
                                                      '-D__CUDA_NO_HALF_OPERATORS__',
                                                      '-D__CUDA_NO_HALF_CONVERSIONS__',
                                                      '-D__CUDA_NO_HALF2_OPERATORS__'] + version_dependent_macros}))

if "--xentropy" in sys.argv or "--cuda_ext" in sys.argv:
    from torch.utils.cpp_extension import CUDAExtension
    if "--xentropy" in sys.argv:
        sys.argv.remove("--xentropy")

    from torch.utils.cpp_extension import BuildExtension
    cmdclass['build_ext'] = BuildExtension

    if torch.utils.cpp_extension.CUDA_HOME is None and not IS_ROCM_PYTORCH:
        raise RuntimeError("--xentropy was requested, but nvcc was not found.  Are you sure your environment has nvcc available?  If you're installing within a container from https://hub.docker.com/r/pytorch/pytorch, only images whose names contain 'devel' will provide nvcc.")
    else:
        print ("INFO: Building the xentropy extension.")
        ext_modules.append(
            CUDAExtension(name='xentropy_cuda',
                          sources=['apex/contrib/csrc/xentropy/interface.cpp',
                                   'apex/contrib/csrc/xentropy/xentropy_kernel.cu'],
                          include_dirs=[os.path.join(this_dir, 'csrc'),
                                        os.path.join(this_dir, 'apex/contrib/csrc/xentropy')],
                          extra_compile_args={'cxx': ['-O3'] + version_dependent_macros,
                                              'nvcc':['-O3'] + version_dependent_macros}))


if "--deprecated_fused_adam" in sys.argv or "--cuda_ext" in sys.argv:
    from torch.utils.cpp_extension import CUDAExtension
    if "--deprecated_fused_adam" in sys.argv:
        sys.argv.remove("--deprecated_fused_adam")

    from torch.utils.cpp_extension import BuildExtension
    cmdclass['build_ext'] = BuildExtension

    if torch.utils.cpp_extension.CUDA_HOME is None and not IS_ROCM_PYTORCH:
        raise RuntimeError("--deprecated_fused_adam was requested, but nvcc was not found.  Are you sure your environment has nvcc available?  If you're installing within a container from https://hub.docker.com/r/pytorch/pytorch, only images whose names contain 'devel' will provide nvcc.")
    else:
        print ("INFO: Building deprecated fused adam extension.")
        nvcc_args_fused_adam = ['-O3', '--use_fast_math'] + version_dependent_macros
        hipcc_args_fused_adam = ['-O3'] + version_dependent_macros
        ext_modules.append(
            CUDAExtension(name='fused_adam_cuda',
                          sources=['apex/contrib/csrc/optimizers/fused_adam_cuda.cpp',
                                   'apex/contrib/csrc/optimizers/fused_adam_cuda_kernel.cu'],
                          include_dirs=[os.path.join(this_dir, 'csrc'),
                                        os.path.join(this_dir, 'apex/contrib/csrc/optimizers')],
                          extra_compile_args={'cxx': ['-O3'] + version_dependent_macros,
                                              'nvcc' : nvcc_args_fused_adam if not IS_ROCM_PYTORCH else hipcc_args_fused_adam}))

if "--deprecated_fused_lamb" in sys.argv or "--cuda_ext" in sys.argv:
    from torch.utils.cpp_extension import CUDAExtension
    if "--deprecated_fused_lamb" in sys.argv:
        sys.argv.remove("--deprecated_fused_lamb")

    from torch.utils.cpp_extension import BuildExtension
    cmdclass['build_ext'] = BuildExtension

    if torch.utils.cpp_extension.CUDA_HOME is None and not IS_ROCM_PYTORCH:
        raise RuntimeError("--deprecated_fused_lamb was requested, but nvcc was not found.  Are you sure your environment has nvcc available?  If you're installing within a container from https://hub.docker.com/r/pytorch/pytorch, only images whose names contain 'devel' will provide nvcc.")
    else:
        print ("INFO: Building deprecated fused lamb extension.")
        nvcc_args_fused_lamb = ['-O3', '--use_fast_math'] + version_dependent_macros
        hipcc_args_fused_lamb = ['-O3'] + version_dependent_macros
        ext_modules.append(
            CUDAExtension(name='fused_lamb_cuda',
                          sources=['apex/contrib/csrc/optimizers/fused_lamb_cuda.cpp',
                                   'apex/contrib/csrc/optimizers/fused_lamb_cuda_kernel.cu',
                                   'csrc/multi_tensor_l2norm_kernel.cu'],
                          include_dirs=[os.path.join(this_dir, 'csrc')],
                          extra_compile_args = nvcc_args_fused_lamb if not IS_ROCM_PYTORCH else hipcc_args_fused_lamb))

# Check, if ATen/CUDAGeneratorImpl.h is found, otherwise use ATen/cuda/CUDAGeneratorImpl.h
# See https://github.com/pytorch/pytorch/pull/70650
generator_flag = []
torch_dir = torch.__path__[0]
if os.path.exists(os.path.join(torch_dir, "include", "ATen", "cuda", "CUDAGeneratorImpl.h")):
    generator_flag = ["-DNEW_GENERATOR_PATH"]

if "--fast_layer_norm" in sys.argv:
    sys.argv.remove("--fast_layer_norm")

    if CUDA_HOME is None and not IS_ROCM_PYTORCH:
        raise RuntimeError("--fast_layer_norm was requested, but nvcc was not found.  Are you sure your environment has nvcc available?  If you're installing within a container from https://hub.docker.com/r/pytorch/pytorch, only images whose names contain 'devel' will provide nvcc.")
    else:
        # Check, if CUDA11 is installed for compute capability 8.0
        cc_flag = []
        _, bare_metal_major, _ = get_cuda_bare_metal_version(CUDA_HOME)
        if int(bare_metal_major) >= 11:
            cc_flag.append('-gencode')
            cc_flag.append('arch=compute_80,code=sm_80')

        ext_modules.append(
            CUDAExtension(name='fast_layer_norm',
                          sources=['apex/contrib/csrc/layer_norm/ln_api.cpp',
                                   'apex/contrib/csrc/layer_norm/ln_fwd_cuda_kernel.cu',
                                   'apex/contrib/csrc/layer_norm/ln_bwd_semi_cuda_kernel.cu',
                                   ],
                          extra_compile_args={'cxx': ['-O3',] + version_dependent_macros + generator_flag,
                                              'nvcc':['-O3',
                                                      '-gencode', 'arch=compute_70,code=sm_70',
                                                      '-U__CUDA_NO_HALF_OPERATORS__',
                                                      '-U__CUDA_NO_HALF_CONVERSIONS__',
                                                      '-U__CUDA_NO_BFLOAT16_OPERATORS__',
                                                      '-U__CUDA_NO_BFLOAT16_CONVERSIONS__',
                                                      '-U__CUDA_NO_BFLOAT162_OPERATORS__',
                                                      '-U__CUDA_NO_BFLOAT162_CONVERSIONS__',
                                                      '-I./apex/contrib/csrc/layer_norm/',
                                                      '--expt-relaxed-constexpr',
                                                      '--expt-extended-lambda',
                                                      '--use_fast_math'] + version_dependent_macros + generator_flag + cc_flag},
                          include_dirs=[os.path.join(this_dir, "apex/contrib/csrc/layer_norm")]))
if "--fmha" in sys.argv:
    sys.argv.remove("--fmha")

    if CUDA_HOME is None and not IS_ROCM_PYTORCH:
        raise RuntimeError("--fmha was requested, but nvcc was not found.  Are you sure your environment has nvcc available?  If you're installing within a container from https://hub.docker.com/r/pytorch/pytorch, only images whose names contain 'devel' will provide nvcc.")
    else:
        # Check, if CUDA11 is installed for compute capability 8.0
        cc_flag = []
        _, bare_metal_major, _ = get_cuda_bare_metal_version(CUDA_HOME)
        if int(bare_metal_major) < 11:
            raise RuntimeError("--fmha only supported on SM80")

        ext_modules.append(
            CUDAExtension(name='fmhalib',
                          sources=[
                                   'apex/contrib/csrc/fmha/fmha_api.cpp',
                                   'apex/contrib/csrc/fmha/src/fmha_noloop_reduce.cu',
                                   'apex/contrib/csrc/fmha/src/fmha_fprop_fp16_128_64_kernel.sm80.cu',
                                   'apex/contrib/csrc/fmha/src/fmha_fprop_fp16_256_64_kernel.sm80.cu',
                                   'apex/contrib/csrc/fmha/src/fmha_fprop_fp16_384_64_kernel.sm80.cu',
                                   'apex/contrib/csrc/fmha/src/fmha_fprop_fp16_512_64_kernel.sm80.cu',
                                   'apex/contrib/csrc/fmha/src/fmha_dgrad_fp16_128_64_kernel.sm80.cu',
                                   'apex/contrib/csrc/fmha/src/fmha_dgrad_fp16_256_64_kernel.sm80.cu',
                                   'apex/contrib/csrc/fmha/src/fmha_dgrad_fp16_384_64_kernel.sm80.cu',
                                   'apex/contrib/csrc/fmha/src/fmha_dgrad_fp16_512_64_kernel.sm80.cu',
                                   ],
                          extra_compile_args={'cxx': ['-O3',
                                                      ] + version_dependent_macros + generator_flag,
                                              'nvcc':['-O3',
                                                      '-gencode', 'arch=compute_80,code=sm_80',
                                                      '-U__CUDA_NO_HALF_OPERATORS__',
                                                      '-U__CUDA_NO_HALF_CONVERSIONS__',
                                                      '--expt-relaxed-constexpr',
                                                      '--expt-extended-lambda',
                                                      '--use_fast_math'] + version_dependent_macros + generator_flag + cc_flag},
                          include_dirs=[os.path.join(this_dir, "apex/contrib/csrc"), os.path.join(this_dir, "apex/contrib/csrc/fmha/src")]))


if "--fast_multihead_attn" in sys.argv or "--cuda_ext" in sys.argv:
    from torch.utils.cpp_extension import CUDAExtension
    if "--fast_multihead_attn" in sys.argv:
        sys.argv.remove("--fast_multihead_attn")

    from torch.utils.cpp_extension import BuildExtension
    cmdclass['build_ext'] = BuildExtension.with_options(use_ninja=False)

    if torch.utils.cpp_extension.CUDA_HOME is None and not IS_ROCM_PYTORCH:
        raise RuntimeError("--fast_multihead_attn was requested, but nvcc was not found.  Are you sure your environment has nvcc available?  If you're installing within a container from https://hub.docker.com/r/pytorch/pytorch, only images whose names contain 'devel' will provide nvcc.")
    else:
        # Check, if CUDA11 is installed for compute capability 8.0
        cc_flag = []
        if not IS_ROCM_PYTORCH:
            _, bare_metal_major, _ = get_cuda_bare_metal_version(cpp_extension.CUDA_HOME)
            if int(bare_metal_major) >= 11:
                cc_flag.append('-gencode')
                cc_flag.append('arch=compute_80,code=sm_80')

        subprocess.run(["git", "submodule", "update", "--init", "apex/contrib/csrc/multihead_attn/cutlass"])
        nvcc_args_mha = ['-O3',
                         '-gencode',
                         'arch=compute_70,code=sm_70',
                         '-Iapex/contrib/csrc/multihead_attn/cutlass',
                         '-U__CUDA_NO_HALF_OPERATORS__',
                         '-U__CUDA_NO_HALF_CONVERSIONS__',
                         '--expt-relaxed-constexpr',
                         '--expt-extended-lambda',
                         '--use_fast_math'] + version_dependent_macros + generator_flag + cc_flag
        hipcc_args_mha = ['-O3',
                          '-Iapex/contrib/csrc/multihead_attn/cutlass',
                          '-I/opt/rocm/include/hiprand',
                          '-I/opt/rocm/include/rocrand',
                          '-U__HIP_NO_HALF_OPERATORS__',
                          '-U__HIP_NO_HALF_CONVERSIONS__'] + version_dependent_macros + generator_flag

        ext_modules.append(
            CUDAExtension(name='fast_additive_mask_softmax_dropout',
                          sources=['apex/contrib/csrc/multihead_attn/additive_masked_softmax_dropout_cpp.cpp',
                                   'apex/contrib/csrc/multihead_attn/additive_masked_softmax_dropout_cuda.cu'],
                          include_dirs=[os.path.join(this_dir, 'csrc'),
                                        os.path.join(this_dir, 'apex/contrib/csrc/multihead_attn')],
                          extra_compile_args={'cxx': ['-O3',] + version_dependent_macros + generator_flag,
                                              'nvcc':nvcc_args_mha if not IS_ROCM_PYTORCH else hipcc_args_mha}))
        ext_modules.append(
            CUDAExtension(name='fast_mask_softmax_dropout',
                          sources=['apex/contrib/csrc/multihead_attn/masked_softmax_dropout_cpp.cpp',
                                   'apex/contrib/csrc/multihead_attn/masked_softmax_dropout_cuda.cu'],
                          include_dirs=[os.path.join(this_dir, 'csrc'),
                                        os.path.join(this_dir, 'apex/contrib/csrc/multihead_attn')],
                          extra_compile_args={'cxx': ['-O3',] + version_dependent_macros + generator_flag,
                                              'nvcc':nvcc_args_mha if not IS_ROCM_PYTORCH else hipcc_args_mha}))
        ext_modules.append(
            CUDAExtension(name='fast_self_multihead_attn_bias_additive_mask',
                          sources=['apex/contrib/csrc/multihead_attn/self_multihead_attn_bias_additive_mask_cpp.cpp',
                                   'apex/contrib/csrc/multihead_attn/self_multihead_attn_bias_additive_mask_cuda.cu'],
                          include_dirs=[os.path.join(this_dir, 'csrc'),
                                        os.path.join(this_dir, 'apex/contrib/csrc/multihead_attn')],
                          extra_compile_args={'cxx': ['-O3',] + version_dependent_macros + generator_flag,
                                              'nvcc':nvcc_args_mha if not IS_ROCM_PYTORCH else hipcc_args_mha}))
        ext_modules.append(
            CUDAExtension(name='fast_self_multihead_attn_bias',
                          sources=['apex/contrib/csrc/multihead_attn/self_multihead_attn_bias_cpp.cpp',
                                   'apex/contrib/csrc/multihead_attn/self_multihead_attn_bias_cuda.cu'],
                          include_dirs=[os.path.join(this_dir, 'csrc'),
                                        os.path.join(this_dir, 'apex/contrib/csrc/multihead_attn')],
                          extra_compile_args={'cxx': ['-O3',] + version_dependent_macros + generator_flag,
                                              'nvcc':nvcc_args_mha if not IS_ROCM_PYTORCH else hipcc_args_mha}))
        ext_modules.append(
            CUDAExtension(name='fast_self_multihead_attn',
                          sources=['apex/contrib/csrc/multihead_attn/self_multihead_attn_cpp.cpp',
                                   'apex/contrib/csrc/multihead_attn/self_multihead_attn_cuda.cu'],
                          include_dirs=[os.path.join(this_dir, 'csrc'),
                                        os.path.join(this_dir, 'apex/contrib/csrc/multihead_attn')],
                          extra_compile_args={'cxx': ['-O3',] + version_dependent_macros + generator_flag,
                                              'nvcc':nvcc_args_mha if not IS_ROCM_PYTORCH else hipcc_args_mha}))
        ext_modules.append(
            CUDAExtension(name='fast_self_multihead_attn_norm_add',
                          sources=['apex/contrib/csrc/multihead_attn/self_multihead_attn_norm_add_cpp.cpp',
                                   'apex/contrib/csrc/multihead_attn/self_multihead_attn_norm_add_cuda.cu'],
                          include_dirs=[os.path.join(this_dir, 'csrc'),
                                        os.path.join(this_dir, 'apex/contrib/csrc/multihead_attn')],
                          extra_compile_args={'cxx': ['-O3',] + version_dependent_macros + generator_flag,
                                              'nvcc':nvcc_args_mha if not IS_ROCM_PYTORCH else hipcc_args_mha}))
        ext_modules.append(
            CUDAExtension(name='fast_encdec_multihead_attn',
                          sources=['apex/contrib/csrc/multihead_attn/encdec_multihead_attn_cpp.cpp',
                                   'apex/contrib/csrc/multihead_attn/encdec_multihead_attn_cuda.cu'],
                          include_dirs=[os.path.join(this_dir, 'csrc'),
                                        os.path.join(this_dir, 'apex/contrib/csrc/multihead_attn')],
                          extra_compile_args={'cxx': ['-O3',] + version_dependent_macros + generator_flag,
                                              'nvcc':nvcc_args_mha if not IS_ROCM_PYTORCH else hipcc_args_mha}))
        ext_modules.append(
            CUDAExtension(name='fast_encdec_multihead_attn_norm_add',
                          sources=['apex/contrib/csrc/multihead_attn/encdec_multihead_attn_norm_add_cpp.cpp',
                                   'apex/contrib/csrc/multihead_attn/encdec_multihead_attn_norm_add_cuda.cu'],
                          include_dirs=[os.path.join(this_dir, 'csrc'),
                                        os.path.join(this_dir, 'apex/contrib/csrc/multihead_attn')],
                          extra_compile_args={'cxx': ['-O3',] + version_dependent_macros + generator_flag,
                                              'nvcc':nvcc_args_mha if not IS_ROCM_PYTORCH else hipcc_args_mha}))

if "--transducer" in sys.argv:
    sys.argv.remove("--transducer")

    if CUDA_HOME is None and not IS_ROCM_PYTORCH:
        raise RuntimeError("--transducer was requested, but nvcc was not found.  Are you sure your environment has nvcc available?  If you're installing within a container from https://hub.docker.com/r/pytorch/pytorch, only images whose names contain 'devel' will provide nvcc.")
    else:
        ext_modules.append(
            CUDAExtension(name='transducer_joint_cuda',
                          sources=['apex/contrib/csrc/transducer/transducer_joint.cpp',
                                   'apex/contrib/csrc/transducer/transducer_joint_kernel.cu'],
                          extra_compile_args={'cxx': ['-O3'] + version_dependent_macros,
                                              'nvcc': ['-O3'] + version_dependent_macros},
                          include_dirs=[os.path.join(this_dir, 'csrc'), os.path.join(this_dir, "apex/contrib/csrc/multihead_attn")]))
        ext_modules.append(
            CUDAExtension(name='transducer_loss_cuda',
                          sources=['apex/contrib/csrc/transducer/transducer_loss.cpp',
                                   'apex/contrib/csrc/transducer/transducer_loss_kernel.cu'],
                          include_dirs=[os.path.join(this_dir, 'csrc')],
                          extra_compile_args={'cxx': ['-O3'] + version_dependent_macros,
                                              'nvcc':['-O3'] + version_dependent_macros}))

if "--fast_bottleneck" in sys.argv:
    sys.argv.remove("--fast_bottleneck")

    if CUDA_HOME is None and not IS_ROCM_PYTORCH:
        raise RuntimeError("--fast_bottleneck was requested, but nvcc was not found.  Are you sure your environment has nvcc available?  If you're installing within a container from https://hub.docker.com/r/pytorch/pytorch, only images whose names contain 'devel' will provide nvcc.")
    else:
        subprocess.run(["git", "submodule", "update", "--init", "apex/contrib/csrc/cudnn-frontend/"])
        ext_modules.append(
            CUDAExtension(name='fast_bottleneck',
                          sources=['apex/contrib/csrc/bottleneck/bottleneck.cpp'],
                          include_dirs=[os.path.join(this_dir, 'apex/contrib/csrc/cudnn-frontend/include')],
                          extra_compile_args={'cxx': ['-O3',] + version_dependent_macros + generator_flag}))

if "--cuda_ext" in sys.argv:
    sys.argv.remove("--cuda_ext")

setup(
    name='apex',
    version='0.1',
    packages=find_packages(exclude=('build',
                                    'csrc',
                                    'include',
                                    'tests',
                                    'dist',
                                    'docs',
                                    'tests',
                                    'examples',
                                    'apex.egg-info',)),
    description='PyTorch Extensions written by NVIDIA',
    ext_modules=ext_modules,
    cmdclass=cmdclass,
    #cmdclass={'build_ext': BuildExtension} if ext_modules else {},
    extras_require=extras,
)
