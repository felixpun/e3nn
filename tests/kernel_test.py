# pylint: disable=C,E1101,E1102
import unittest

import torch

from e3nn.kernel import Kernel, KernelFn
from e3nn.radial import ConstantRadialModel
from e3nn import rs, o3


class Tests(unittest.TestCase):
    def test1(self):
        torch.set_default_dtype(torch.float64)
        Rs_in = [(1, 0), (1, 1), (2, 0), (1, 2)]
        Rs_out = [(2, 0), (1, 1), (1, 2), (3, 0)]
        kernel = Kernel(Rs_in, Rs_out, ConstantRadialModel)

        n_path = 0
        for mul_out, l_out, p_out in kernel.Rs_out:
            for mul_in, l_in, p_in in kernel.Rs_in:
                l_filters = kernel.get_l_filters(l_in, p_in, l_out, p_out)
                n_path += mul_out * mul_in * len(l_filters)

        for rg_Y, rg_R in [(True, True), (True, False), (False, True)]:
            r = torch.randn(2, 3)
            radii = r.norm(2, dim=1)  # [batch]
            Y = kernel.sh(kernel.set_of_l_filters, r)  # [l_filter * m_filter, batch]
            Y = Y.clone().detach().requires_grad_(rg_Y)
            R = torch.randn(2, n_path, requires_grad=rg_R)  # [batch, l_out * l_in * mul_out * mul_in * l_filter]
            norm_coef = kernel.norm_coef
            norm_coef = norm_coef[:, :, (radii == 0).type(torch.long)]  # [l_out, l_in, batch]

            inputs = (
                Y, R, norm_coef, kernel.Rs_in, kernel.Rs_out, kernel.get_l_filters, kernel.set_of_l_filters
            )
            self.assertTrue(torch.autograd.gradcheck(KernelFn.apply, inputs))

    def test_equiv(self):
        torch.set_default_dtype(torch.float64)
        Rs_in = [(5, 0), (15, 1), (5, 0), (10, 2)]
        Rs_out = [(2, 0), (1, 1), (1, 2), (3, 0)]

        ker = Kernel(Rs_in, Rs_out, ConstantRadialModel)
        r = torch.randn(10, 3)

        a = torch.randn(3)
        y1 = torch.einsum('zij,jk->zik', ker(torch.einsum('ij,zj->zi', o3.rot(*a), r)), rs.rep(Rs_in, *a))
        y2 = torch.einsum('ki,zij->zkj', rs.rep(Rs_out, *a), ker(r))

        self.assertLess((y1 - y2).abs().max(), 1e-10)


class TestCompare(unittest.TestCase):
    def setUp(self):
        super(TestCompare, self).setUp()
        torch.set_default_dtype(torch.float64)
        torch.backends.cudnn.deterministic = True
        self.Rs_in = [(1, 0), (1, 1), (2, 0), (1, 2)]
        self.Rs_out = [(2, 0), (1, 1), (1, 2), (3, 0)]

        batch = 100
        atoms = 40
        self.geometry = torch.rand(batch, atoms, 3)

        self.msg = "Kernel parameters were not identical. This means the test cannot compare outputs."

    def test_compare_forward(self):
        for normalization in ["norm", "component"]:
            torch.manual_seed(0)
            K = Kernel(self.Rs_in, self.Rs_out, RadialModel=ConstantRadialModel, normalization=normalization)
            new_features = K(self.geometry)

            torch.manual_seed(0)
            K2 = Kernel(self.Rs_in, self.Rs_out, RadialModel=ConstantRadialModel, normalization=normalization)
            check_new_features = K2(self.geometry, custom_backward=True)

            assert all(torch.all(a == b) for a, b in zip(K.parameters(), K.parameters())), self.msg
            self.assertTrue(torch.allclose(new_features, check_new_features))


if __name__ == '__main__':
    unittest.main()
