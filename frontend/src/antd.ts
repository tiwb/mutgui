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
import { register } from './registry';
import { VirtualList } from './virtual-list';

/** 注册常用 Ant Design 组件。 */
export function registerAntd(): void {
  register('Input', Input);
  register('InputNumber', InputNumber);
  register('Checkbox', Checkbox);
  register('Select', Select);
  register('Button', Button);
  register('Slider', Slider);
  register('Switch', Switch);
  register('DatePicker', DatePicker);
  register('Radio', Radio);
  // Input 子组件
  register('Input.TextArea', Input.TextArea);
  register('Input.Password', Input.Password);
  // Radio 子组件
  register('Radio.Group', Radio.Group);
  // Form
  register('Form', Form);
  register('Form.Item', Form.Item);
  // Typography
  register('Typography', Typography);
  register('Typography.Text', Typography.Text);
  register('Typography.Title', Typography.Title);
  register('Typography.Paragraph', Typography.Paragraph);
  // Layout
  register('Card', Card);
  register('Row', Row);
  register('Col', Col);
  register('Space', Space);
  register('Divider', Divider);
  // mutgui 自定义组件
  register('VirtualList', VirtualList);
}
