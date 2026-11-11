
/****** Object:  Table [dbo].[MFG_MoveOrder]    Script Date: 13/10/2026 5:10:05 PM ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[MFG_MoveOrder](
	[MaXuong] [nvarchar](10) NOT NULL,
	[SoChungTu] [nvarchar](20) NOT NULL,
	[Ngay] [datetime] NULL,
	[GhiChu] [nvarchar](150) NULL,
	[STT] [int] NULL,
	[MaVatTu] [nvarchar](20) NULL,
	[DVT] [nvarchar](10) NULL,
	[SoLuong] [numeric](18, 6) NULL,
	[MaKho] [nvarchar](20) NULL,
	[UserID] [nvarchar](20) NULL,
	[GhiChuD] [nvarchar](100) NULL,
	[MaDonVi] [nvarchar](20) NULL,
	[LSX] [nvarchar](20) NULL,
	[XuatBu] [char](1) NULL,
	[SoDMPH] [nvarchar](50) NULL,
	[YCBoSung] [nchar](1) NULL,
	[NhomCD] [nvarchar](20) NULL,
	[CongDoan] [int] NULL,
	[HeSoBom] [numeric](18, 4) NULL,
	[SoQCSP] [nvarchar](20) NULL,
	[SoLuongYC] [numeric](18, 4) NULL,
	[TinhTrang] [nvarchar](2) NULL,
	[SoLuongBom] [numeric](38, 6) NULL,
	[DinhLuong] [numeric](18, 6) NULL,
	[HaoHut] [numeric](18, 6) NULL,
	[CongThuc] [nvarchar](200) NULL,
	[ChuoiCongThuc] [nvarchar](200) NULL,
	[ModifyDate] [datetime] NULL,
	[KhoSXSuaDoi] [numeric](18, 4) NULL,
	[MaCD] [nvarchar](10) NULL,
	[MaCDBS] [nvarchar](10) NULL,
	[LoiNhuanGross] [numeric](18, 4) NULL,
	[MaThanhPham] [nvarchar](20) NULL,
	[VerNL_CTG] [int] NULL,
	[NotDrillDown_CTG] [char](1) NULL,
	[MaTPBTP_CTG] [nvarchar](20) NULL,
	[VerTPBTP_CTG] [int] NULL,
	[HSBOMNL_CTG] [numeric](18, 4) NULL,
	[SoQCSPNL_CTG] [nvarchar](50) NULL,
	[BDTPNL_CTG] [numeric](18, 4) NULL,
	[KhoTKNL_CTG] [numeric](18, 4) NULL,
	[ConNgangNL_CTG] [numeric](18, 4) NULL,
	[LLSP] [nvarchar](100) NULL,
	[MaNCC] [nvarchar](50) NULL,
	[LuuYKhac] [nvarchar](2000) NULL,
	[MaVTBOM] [nvarchar](20) NULL
)
GO

ALTER TABLE [dbo].[MFG_MoveOrder] ADD  CONSTRAINT [DF_MFG_MoveOrder_ModifyDate]  DEFAULT (getdate()) FOR [ModifyDate]
GO


