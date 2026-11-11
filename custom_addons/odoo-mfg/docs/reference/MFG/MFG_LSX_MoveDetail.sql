
/****** Object:  Table [dbo].[MFG_LSX_MoveDetail]    Script Date: 13/10/2026 5:08:25 PM ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[MFG_LSX_MoveDetail](
	[LSX] [nvarchar](50) NOT NULL,
	[CongDoan] [int] NOT NULL,
	[Item] [nvarchar](20) NOT NULL,
	[SoLuong] [numeric](18, 6) NOT NULL,
	[ThanhTien] [numeric](18, 0) NOT NULL,
	[LineType] [char](1) NOT NULL,
	[Ngay] [datetime] NOT NULL,
	[ID] [int] NOT NULL,
	[Move] [int] NOT NULL,
	[MaKho] [nvarchar](20) NULL,
	[TaiKhoanDoiUng] [nvarchar](10) NULL,
	[TaiKhoan] [nvarchar](10) NULL,
	[KhoanMuc] [nvarchar](20) NULL,
	[MaLocator] [nvarchar](20) NULL,
	[SoMetDai] [numeric](18, 4) NULL,
	[SoLuongKH] [numeric](18, 6) NULL,
	[SoLuongGiaoDich] [numeric](20, 6) NULL
)
GO


