

/****** Object:  Table [dbo].[MFG_NHAPKHOTP_XUONG]    Script Date: 13/10/2026 5:10:24 PM ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[MFG_NHAPKHOTP_XUONG](
	[LSX] [nvarchar](20) NULL,
	[MaVatTu] [nvarchar](50) NULL,
	[DVT] [nvarchar](10) NULL,
	[SoLuong] [numeric](18, 4) NULL,
	[SoLo] [nvarchar](50) NULL,
	[HanSuDung] [datetime] NULL,
	[Ngay] [datetime] NULL,
	[MaKho] [nvarchar](50) NULL,
	[SoPhieuNhap] [nvarchar](50) NULL,
	[SoPhieuXuat] [nvarchar](50) NULL,
	[SoDeNghi] [nvarchar](50) NULL,
	[TinhTrang] [nvarchar](50) NULL,
	[DienGiai] [nvarchar](250) NULL,
	[MaBoPhan] [nvarchar](50) NULL,
	[MaDonVi] [nvarchar](50) NULL,
	[MaDan] [nvarchar](20) NULL,
	[TrucHo] [nvarchar](20) NULL,
	[Ca] [nvarchar](20) NULL,
	[MaKhoBu] [nvarchar](50) NULL,
	[SoLuongBu] [numeric](18, 4) NULL,
	[SoLuongCDT] [numeric](18, 4) NULL,
	[SoLuongKg] [numeric](18, 4) NULL,
	[HeSo] [numeric](18, 6) NULL,
	[NgaySX] [datetime] NULL,
	[GhiChu] [nvarchar](250) NULL,
	[CanDong] [nvarchar](1) NULL,
	[UserID] [nvarchar](50) NULL,
	[ModifyDate] [datetime] NULL,
	[ChkNhapKhac] [nvarchar](1) NULL,
	[SoLuongMD] [numeric](18, 4) NULL,
	[MaLocator] [nvarchar](100) NULL
) ON [PRIMARY]
GO


