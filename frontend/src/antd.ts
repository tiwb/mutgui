/**
 * Ant Design 适配 — 批量注册 Ant Design 组件到 mutgui registry。
 */
import {
  Input,
  InputNumber,
  Checkbox,
  Select,
  Button,
  Slider,
  Switch,
  DatePicker,
  Radio,
  Form,
  Typography,
  Card,
  Row,
  Col,
  Space,
  Divider,
} from 'antd';
import { registerComponents } from './registry';
import { VirtualList } from './virtual-list';

/** 注册常用 Ant Design 组件。 */
export function registerAntd(): void {
  registerComponents({
    Input,
    InputNumber,
    Checkbox,
    Select,
    Button,
    Slider,
    Switch,
    DatePicker,
    Radio,
    VirtualList,
  });
  registerComponents({
    __name__: 'Input',
    TextArea: Input.TextArea,
    Password: Input.Password,
  });
  registerComponents({
    __name__: 'Radio',
    Group: Radio.Group,
  });
  registerComponents({
    __name__: 'Form',
    Item: Form.Item,
  });
  registerComponents({
    Form,
    Typography,
    Card,
    Row,
    Col,
    Space,
    Divider,
  });
  registerComponents({
    __name__: 'Typography',
    Text: Typography.Text,
    Title: Typography.Title,
    Paragraph: Typography.Paragraph,
  });
}
