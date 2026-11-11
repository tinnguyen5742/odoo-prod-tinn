
/****** Object:  Table [dbo].[MFG_LSX]    Script Date: 13/10/2026 5:06:05 PM ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[MFG_LSX](
	[LSX] [nvarchar](50) NOT NULL,
	[LSX_Father] [nvarchar](50) NULL,
	[MaVatTu] [nvarchar](20) NOT NULL,
	[MaBoPhan] [nvarchar](10) NOT NULL,
	[Version] [int] NOT NULL,
	[NgayBatDau] [datetime] NOT NULL,
	[NgayKetThuc] [datetime] NULL,
	[SoLuong] [numeric](18, 4) NOT NULL,
	[TinhTrang] [char](1) NOT NULL,
	[DienGiai] [nvarchar](150) NULL,
	[SoSO] [nvarchar](20) NULL,
	[DungSai] [numeric](18, 4) NULL,
	[UserCreate] [nvarchar](20) NULL,
	[DateCreate] [datetime] NULL,
	[MaCa] [nvarchar](20) NULL,
	[Type] [char](1) NULL,
	[GhiChu] [nvarchar](500) NULL,
	[NgayGiao] [datetime] NULL,
	[SoQCSP] [nvarchar](20) NULL,
	[LSXTuiThamChieu] [nvarchar](20) NULL,
	[DungSaiDuoi] [numeric](18, 4) NULL,
	[NgayDatHang] [datetime] NULL,
	[ModifyDate] [datetime] NULL,
	[NgayDong] [nvarchar](10) NULL,
	[HeSo] [numeric](18, 6) NULL,
	[SOSO_THAMCHIEU] [nvarchar](20) NULL,
	[LSX_THAMCHIEU] [nvarchar](200) NULL,
	[MAVT_THAMCHIEU] [nvarchar](20) NULL,
	[SoLuongMetDai] [numeric](18, 4) NULL,
	[InTocDoMay] [numeric](18, 4) NULL,
	[SoPO] [nvarchar](50) NULL,
	[MaKH] [nvarchar](50) NULL,
	[SoSOTC] [nvarchar](50) NULL
) ON [PRIMARY]
GO

ALTER TABLE [dbo].[MFG_LSX] ADD  CONSTRAINT [DF_MFG_LSX_HeSo]  DEFAULT ((1)) FOR [HeSo]
GO

EXEC sys.sp_addextendedproperty @name=N'MS_Description', @value=N'C: sx chinh; D: dieu chinh' , @level0type=N'SCHEMA',@level0name=N'dbo', @level1type=N'TABLE',@level1name=N'MFG_LSX', @level2type=N'COLUMN',@level2name=N'Type'
GO


