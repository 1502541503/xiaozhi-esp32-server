package xiaozhi.modules.device.entity;

import lombok.Data;

@Data
public class ResponseWrapper<T> {

    private int code;
    private T data;
    private String mesg;
}
