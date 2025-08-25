package xiaozhi.modules.device.entity;

import com.baomidou.mybatisplus.annotation.*;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.EqualsAndHashCode;

import java.util.Date;

@Data
@EqualsAndHashCode(callSuper = false)
@TableName("ble_white_list")
@Schema(description = "设备信息")
public class BleWhiteList {

    @TableId(type = IdType.AUTO)
    @Schema(description = "ID")
    private String id;

    @Schema(description = "appid")
    private String pid;

    @Schema(description = "蓝牙名")
    private String bleName;

    @Schema(description = "固件标记")
    private String flag;

    @Schema(description = "备注")
    private String remark;

    @Schema(description = "更新者")
    @TableField(fill = FieldFill.UPDATE)
    private Long updater;

    @Schema(description = "更新时间")
    @TableField(fill = FieldFill.UPDATE)
    private Date updateDate;

    @Schema(description = "创建者")
    @TableField(fill = FieldFill.INSERT)
    private Long creator;

    @Schema(description = "创建时间")
    @TableField(fill = FieldFill.INSERT)
    private Date createDate;
}