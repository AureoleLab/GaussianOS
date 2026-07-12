"""Exercise gsplat's native sm_120 forward and backward kernels."""

from __future__ import annotations

import json

import torch

import gsplat
import gsplat.csrc as csrc
from gsplat import rasterization


def main() -> int:
    torch.manual_seed(7)
    device = "cuda"
    means = torch.tensor(
        [[0.0, 0.0, 2.0], [0.25, 0.0, 2.2], [-0.2, 0.1, 1.8]],
        device=device,
        requires_grad=True,
    )
    quats = torch.tensor(
        [[1.0, 0.0, 0.0, 0.0]] * 3, device=device, requires_grad=True
    )
    scales = torch.tensor(
        [[0.08, 0.12, 0.16], [0.11, 0.07, 0.15], [0.09, 0.14, 0.06]],
        device=device,
        requires_grad=True,
    )
    opacities = torch.full((3,), 0.8, device=device, requires_grad=True)
    colors = torch.tensor(
        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        device=device,
        requires_grad=True,
    )
    viewmats = torch.eye(4, device=device)[None]
    intrinsics = torch.tensor(
        [[[80.0, 0.0, 32.0], [0.0, 80.0, 32.0], [0.0, 0.0, 1.0]]],
        device=device,
    )
    renders, alphas, _ = rasterization(
        means,
        quats,
        scales,
        opacities,
        colors,
        viewmats,
        intrinsics,
        64,
        64,
    )
    loss = renders.square().mean() + alphas.mean()
    loss.backward()
    gradients = {
        "means": means.grad,
        "quats": quats.grad,
        "scales": scales.grad,
        "opacities": opacities.grad,
        "colors": colors.grad,
    }
    result = {
        "gsplat": gsplat.__version__,
        "native_extension": csrc.__file__,
        "render_shape": list(renders.shape),
        "alpha_shape": list(alphas.shape),
        "loss": float(loss.detach()),
        "gradient_norms": {
            name: float(value.norm()) for name, value in gradients.items()
        },
        "finite": bool(
            torch.isfinite(renders).all()
            and all(torch.isfinite(value).all() for value in gradients.values())
        ),
        "device": torch.cuda.get_device_name(0),
        "capability": list(torch.cuda.get_device_capability(0)),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["finite"] and all(result["gradient_norms"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
