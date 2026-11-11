

/****** Object:  Table [dbo].[MFG_NHAPKHOTP_KD]    Script Date: 13/10/2026 5:11:37 PM ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[MFG_NHAPKHOTP_KD](
	[LSX] [nvarchar](50) NULL,
	[MaVatTu] [nvarchar](50) NULL,
	[DVT] [nvarchar](50) NULL,
	[SoLuong] [numeric](18, 4) NULL,
	[SoLo] [nvarchar](50) NULL,
	[HanSuDung] [datetime] NULL,
	[Ngay] [datetime] NULL,
	[MaKho] [nvarchar](50) NULL,
	[SoPhieuNhap] [nvarchar](50) NULL,
	[SoDeNghi] [nvarchar](50) NULL,
	[TinhTrang] [char](10) NULL,
	[DienGiai] [nvarchar](250) NULL,
	[MaBoPhan] [nvarchar](50) NULL,
	[MaDonVi] [nvarchar](50) NULL,
	[MaDan] [nvarchar](20) NULL,
	[TrucHo] [nvarchar](20) NULL,
	[Ca] [nvarchar](20) NULL,
	[SoQA] [nvarchar](20) NULL,
	[MaKhoBu] [nvarchar](50) NULL,
	[SoLuongBu] [numeric](18, 4) NULL,
	[NgaySX] [datetime] NULL,
	[SoLuongCDT] [numeric](18, 4) NULL,
	[SoLuongDeNghi] [numeric](18, 4) NULL,
	[SoLuongKg] [numeric](18, 4) NULL,
	[HeSo] [numeric](18, 6) NULL,
	[LoaiCT] [nvarchar](20) NULL,
	[ModifyDate] [timestamp] NOT NULL,
	[IDTime] [datetime] NULL,
	[ChkNhapKhac] [nvarchar](1) NULL,
	[Malocator] [nvarchar](50) NULL,
	[SoLuongMD] [numeric](18, 4) NULL,
	[SoPO] [nvarchar](50) NULL,
	[DonGiaPO] [numeric](18, 4) NULL,
	[ThanhTienPO] [numeric](18, 4) NULL
) ON [PRIMARY]
GO

ALTER TABLE [dbo].[MFG_NHAPKHOTP_KD] ADD  CONSTRAINT [DF_MFG_NHAPKHOTP_KD_IDTime]  DEFAULT (getdate()) FOR [IDTime]
GO


