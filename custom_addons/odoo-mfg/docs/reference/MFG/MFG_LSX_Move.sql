

/****** Object:  Table [dbo].[MFG_LSX_Move]    Script Date: 13/10/2026 5:07:31 PM ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[MFG_LSX_Move](
	[LSX] [nvarchar](50) NOT NULL,
	[CongDoan] [int] NOT NULL,
	[SoLuong] [numeric](18, 4) NOT NULL,
	[ThanhTien] [numeric](18, 0) NOT NULL,
	[Ngay] [datetime] NOT NULL,
	[ID] [int] NOT NULL,
	[NX] [int] NOT NULL,
	[Move] [int] NOT NULL,
	[Loai] [nvarchar](20) NULL,
	[SoYCCP] [nvarchar](20) NULL,
	[SoLuongMD] [numeric](18, 4) NULL,
	[HeSo] [numeric](18, 4) NULL,
	[SLCDTruoc] [numeric](18, 4) NULL,
	[SLMDCDTruoc] [numeric](18, 4) NULL,
	[CaSX] [nvarchar](50) NULL,
	[DongCD] [int] NULL,
	[ModifyDate] [timestamp] NOT NULL,
	[IDTime] [datetime] NULL,
	[UserID] [nvarchar](20) NULL
) ON [PRIMARY]
GO

ALTER TABLE [dbo].[MFG_LSX_Move] ADD  CONSTRAINT [DF_MFG_LSX_Move_IDTime]  DEFAULT (getdate()) FOR [IDTime]
GO


